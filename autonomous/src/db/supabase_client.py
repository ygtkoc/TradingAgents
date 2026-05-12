"""Cached Supabase service-role client."""
from __future__ import annotations

import base64
import json
from functools import lru_cache

from supabase import Client, create_client

from src.config import settings
from src.logging_config import get_logger

log = get_logger(__name__)


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
            "SUPABASE_SERVICE_ROLE_KEY is required for autonomous startup; "
            "refusing to fall back to anon credentials."
        )
    if key.startswith("sb_publishable_"):
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY contains a publishable/anon key; "
            "autonomous requires the Supabase service_role secret."
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
                "Check that autonomous is loading SUPABASE_SERVICE_ROLE_KEY from its own .env."
            ) from exc
        raise RuntimeError(
            "Supabase startup self-test failed for table paper_accounts: "
            f"{message}"
        ) from exc


@lru_cache(maxsize=1)
def get_client() -> Client:
    _assert_service_role_configuration()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
