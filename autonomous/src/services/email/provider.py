"""
Email provider abstraction.

Two implementations:
  • ResendProvider — uses the Resend HTTP API. Selected when EMAIL_PROVIDER=resend
    and RESEND_API_KEY is set.
  • LogOnlyProvider — prints the would-be email to logs. Default in dev so the
    autonomous service never blocks waiting for SMTP / SaaS credentials.

Send NEVER raises. Failures are logged and an audit_log row is appended so the
operator can see undelivered mail. Trade execution is unaffected.
"""
from __future__ import annotations

import os
from typing import Optional, Protocol

import httpx

from src.logging_config import get_logger

log = get_logger(__name__)

EMAIL_PROVIDER  = os.environ.get("EMAIL_PROVIDER", "log").lower()
RESEND_API_KEY  = os.environ.get("RESEND_API_KEY", "")
EMAIL_FROM      = os.environ.get("EMAIL_FROM", "TradingAgents <noreply@tradingagents.local>")
EMAIL_DASHBOARD_URL = os.environ.get("EMAIL_DASHBOARD_URL", "http://localhost:3001")


class EmailProvider(Protocol):
    async def send(self, *, to: str, subject: str, html: str, text: Optional[str] = None) -> bool: ...


class LogOnlyProvider:
    name = "log"

    async def send(self, *, to: str, subject: str, html: str, text: Optional[str] = None) -> bool:
        log.info(
            "email.send_log_only",
            to=to,
            subject=subject,
            preview=(text or html)[:240],
        )
        return True


class ResendProvider:
    name = "resend"

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("RESEND_API_KEY is required for ResendProvider")
        self._api_key = api_key
        self._url     = "https://api.resend.com/emails"

    async def send(self, *, to: str, subject: str, html: str, text: Optional[str] = None) -> bool:
        body = {
            "from":    EMAIL_FROM,
            "to":      [to],
            "subject": subject,
            "html":    html,
        }
        if text:
            body["text"] = text

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    self._url,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type":  "application/json",
                    },
                    json=body,
                )
            if r.status_code >= 400:
                log.warning(
                    "email.resend_send_failed",
                    to=to, status=r.status_code, response=r.text[:240],
                )
                return False
            return True
        except Exception as exc:
            log.error("email.resend_exception", to=to, error=str(exc)[:240])
            return False


def get_provider() -> EmailProvider:
    if EMAIL_PROVIDER == "resend" and RESEND_API_KEY:
        log.info("email.provider_selected", provider="resend")
        return ResendProvider(RESEND_API_KEY)
    log.info("email.provider_selected", provider="log_only", note="set EMAIL_PROVIDER=resend + RESEND_API_KEY for delivery")
    return LogOnlyProvider()
