"""Singleton supabase-py client for the Position Engine."""
from __future__ import annotations

import base64
import json

from supabase import Client, create_client

from src.config import settings
from src.logging_config import get_logger

log = get_logger(__name__)

_client: Client | None = None


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
            "SUPABASE_SERVICE_ROLE_KEY is required for position-engine startup; "
            "refusing to fall back to anon credentials."
        )
    if key.startswith("sb_publishable_"):
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY contains a publishable/anon key; "
            "position-engine requires the Supabase service_role secret."
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
                "Check that position-engine is loading SUPABASE_SERVICE_ROLE_KEY from its own .env."
            ) from exc
        raise RuntimeError(
            "Supabase startup self-test failed for table paper_accounts: "
            f"{message}"
        ) from exc


def get_client() -> Client:
    global _client
    _assert_service_role_configuration()
    if _client is None:
        _client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
    return _client
