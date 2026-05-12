"""
Supabase service-role client factory.

Rules:
  - Only one client instance per process (singleton).
  - SUPABASE_SERVICE_ROLE_KEY is NEVER logged.
  - This module must never be imported from any client-facing code.
  - All reads/writes bypass RLS (service_role) — caller is responsible
    for ownership/permission checks in repository layer.

HTTP/2 note:
  Local Supabase (Docker) does not reliably support HTTP/2. We pass
  `http2=False` via httpx transport options to prevent
  `RemoteProtocolError: Server disconnected` on connection reuse.
  `execute_with_retry` additionally catches such errors and resets the
  client singleton so the next attempt uses a fresh connection pool.
"""
from __future__ import annotations

import asyncio
import base64
import json
import time
from typing import Optional

from supabase import Client, create_client

from src.config import settings
from src.logging_config import get_logger

log = get_logger(__name__)

# ── httpx import (optional — graceful degradation if not installed) ──────────
try:
    import httpx as _httpx
    _HTTPX_RETRYABLE = (
        _httpx.RemoteProtocolError,
        _httpx.ConnectError,
        _httpx.NetworkError,
        _httpx.ReadError,
        _httpx.WriteError,
    )
except ImportError:
    _httpx = None           # type: ignore[assignment]
    _HTTPX_RETRYABLE = ()

# All exception types that warrant a transparent retry + client reset.
_RETRYABLE_ERRORS = (
    ConnectionError,
    ConnectionResetError,
    TimeoutError,
    OSError,
) + _HTTPX_RETRYABLE

# Module-level singleton
_client: Optional[Client] = None
_client_lock = asyncio.Lock()


def _decode_jwt_payload(token: str) -> dict[str, object] | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload + padding)
        return json.loads(raw.decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return None


def _assert_service_role_configuration() -> None:
    key = settings.supabase_service_role_key.strip()
    if not key:
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY is required for agent-engine startup; "
            "refusing to fall back to anon credentials."
        )
    if key.startswith("sb_publishable_"):
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY contains a publishable/anon key; "
            "agent-engine requires the Supabase service_role secret."
        )

    payload = _decode_jwt_payload(key)
    if payload is not None and payload.get("role") != "service_role":
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY is not a service_role token; "
            f"decoded role={payload.get('role')!r}."
        )


def log_startup_auth() -> None:
    _assert_service_role_configuration()
    log.info(
        "supabase.auth_configured",
        supabase_auth_mode="service_role",
        supabase_url=settings.supabase_url,
        service_key_present=True,
    )


def run_startup_self_test() -> None:
    _assert_service_role_configuration()
    try:
        get_client().table("paper_accounts").select("id").limit(1).execute()
    except Exception as exc:
        message = str(exc)
        if "403" in message or "Forbidden" in message:
            raise RuntimeError(
                "Supabase startup self-test failed for table paper_accounts: "
                "received 403 Forbidden while using service_role credentials. "
                "Check that agent-engine is loading SUPABASE_SERVICE_ROLE_KEY from its own .env."
            ) from exc
        raise RuntimeError(
            "Supabase startup self-test failed for table paper_accounts: "
            f"{message}"
        ) from exc


def _create_client_instance() -> Client:
    """Create a new Supabase client with HTTP/2 disabled.

    HTTP/2 is explicitly disabled via httpx transport options because local
    Supabase (Docker) does not reliably negotiate HTTP/2 and raises
    `RemoteProtocolError: Server disconnected` on persistent connection reuse.
    """
    _assert_service_role_configuration()
    log.info("supabase_client.init", url=settings.supabase_url, http2=False)

    client = create_client(
        supabase_url=settings.supabase_url,
        supabase_key=settings.supabase_service_role_key,
    )

    # Patch the underlying httpx session to disable HTTP/2 if possible.
    # supabase-py v2 exposes the PostgREST session as client.postgrest._session.
    # This is best-effort: if the attribute path changes in a future version,
    # we fall back silently (the retry mechanism still handles disconnects).
    if _httpx is not None:
        try:
            for attr in ("postgrest", "_postgrest"):
                pg = getattr(client, attr, None)
                if pg is not None and hasattr(pg, "_session"):
                    old_session = pg._session
                    pg._session = _httpx.Client(
                        http2=False,
                        timeout=old_session.timeout if hasattr(old_session, "timeout") else 30.0,
                        headers=dict(old_session.headers) if hasattr(old_session, "headers") else {},
                    )
                    log.info("supabase_client.http2_disabled")
                    break
        except Exception as exc:
            log.debug("supabase_client.http2_patch_skipped", reason=str(exc)[:200])

    return client


def reset_client() -> None:
    """Force recreation of the singleton on next `get_client()` call.

    Called after connection-level errors (HTTP/2 disconnect, ECONNRESET) so
    the next DB operation starts with a fresh httpx connection pool instead of
    reusing a broken persistent connection.
    """
    global _client
    _client = None
    log.warning("supabase_client.reset", reason="connection_error")


def get_client() -> Client:
    """Returns the module-level synchronous Supabase service client.

    Thread-safe via double-checked locking (fast path: no lock when already
    initialised). HTTP/2 is disabled; see `_create_client_instance()`.
    """
    global _client
    _assert_service_role_configuration()
    if _client is None:
        _client = _create_client_instance()
    return _client


async def get_client_async() -> Client:
    """Async-safe client access for use in async contexts."""
    global _client
    _assert_service_role_configuration()
    if _client is None:
        async with _client_lock:
            if _client is None:
                _client = await asyncio.to_thread(_create_client_instance)
    return _client


def execute_with_retry(fn, *args, **kwargs):
    """Retry transient Supabase / httpx errors with exponential back-off.

    On each retryable error the client singleton is reset so the next attempt
    opens a fresh TCP connection rather than reusing the broken one.

    Catches:
      • ConnectionError / ConnectionResetError / TimeoutError / OSError
      • httpx.RemoteProtocolError  (HTTP/2 "Server disconnected")
      • httpx.ConnectError / NetworkError / ReadError / WriteError

    Non-retryable errors propagate immediately without resetting the client.
    """
    last_exc: Optional[Exception] = None
    delays = [1.0, 3.0, 8.0]   # 3 attempts, exponential-ish delay

    for attempt, delay in enumerate(delays, start=1):
        try:
            return fn(*args, **kwargs)
        except _RETRYABLE_ERRORS as exc:
            last_exc = exc
            log.warning(
                "db.write.retry",
                attempt=attempt,
                max_attempts=len(delays),
                error_type=type(exc).__name__,
                error=str(exc)[:200],
            )
            reset_client()                       # fresh connection next attempt
            if attempt < len(delays):
                time.sleep(delay)
        except Exception:
            raise                                # non-retryable — propagate now

    log.error(
        "db.write.failed",
        error_type=type(last_exc).__name__ if last_exc else "unknown",
        error=str(last_exc)[:300] if last_exc else "",
        hint="Signal/decision write exhausted all retries; worker continues.",
    )
    raise last_exc  # type: ignore[misc]
