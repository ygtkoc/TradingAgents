"""
EmailDispatcher worker.

Polls `trade_events` for paper open/close events that have NOT yet been
flagged as emailed. For each:
  • loads the corresponding trade,
  • resolves the user's email via auth.users (admin API),
  • renders the template,
  • sends via the configured provider (Resend or log-only),
  • marks the event as emailed by writing `metadata.emailed_at` on the row.

Failures are recorded in `audit_logs` (best-effort) — they NEVER block trade
execution because this dispatcher runs out-of-band from the engines.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from src.config import settings
from src.db.repositories import AuditLogRepository
from src.db.supabase_client import get_client
from src.heartbeat import tracker
from src.logging_config import get_logger
from src.services.email.provider import EmailProvider, get_provider
from src.services.email.renderer import render_trade_email
from src.utils.time import utcnow_iso
from src.worker import Worker

log = get_logger(__name__)

HEARTBEAT_NAME      = "email_dispatcher"
EVENT_TYPES_OF_INTEREST = ("paper_order_filled", "trade_opened", "trade_closed")
LOOKBACK_MINUTES    = 30
MAX_EMAILS_PER_TICK = 25


async def _run(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


class EmailDispatcher(Worker):
    name             = HEARTBEAT_NAME
    interval_seconds = 15.0

    def __init__(
        self,
        provider: Optional[EmailProvider] = None,
    ) -> None:
        super().__init__()
        self._client   = get_client()
        self._provider = provider or get_provider()
        self._audit    = AuditLogRepository()

    async def tick(self) -> None:
        try:
            events = await self._fetch_pending_events()
        except Exception as exc:
            log.error("email_dispatcher.fetch_failed", error=str(exc)[:240])
            tracker.beat(self.name, "error", error=str(exc)[:200])
            return

        if not events:
            self.beat_ok(pending=0)
            return

        sent = 0
        for ev in events[:MAX_EMAILS_PER_TICK]:
            ok = await self._dispatch_one(ev)
            if ok:
                sent += 1

        self.beat_ok(pending=len(events), sent=sent)

    # ── Internal helpers ─────────────────────────────────────────────────────

    async def _fetch_pending_events(self) -> list[dict[str, Any]]:
        from datetime import datetime, timedelta, timezone
        since = (datetime.now(timezone.utc) - timedelta(minutes=LOOKBACK_MINUTES)).isoformat()

        def _q():
            # NOTE: trade_events does NOT have a `details` column — only
            # metadata (jsonb), event_type, trade_id, created_at.
            return (
                self._client.table("trade_events")
                .select("id,trade_id,user_id,event_type,metadata,created_at")
                .in_("event_type", list(EVENT_TYPES_OF_INTEREST))
                .gte("created_at", since)
                .order("created_at", desc=False)
                .limit(MAX_EMAILS_PER_TICK * 4)
                .execute()
            )
        result = await _run(_q)
        rows = result.data or []
        return [r for r in rows if not (r.get("metadata") or {}).get("emailed_at")]

    async def _dispatch_one(self, event: dict[str, Any]) -> bool:
        trade_id = event.get("trade_id")
        if not trade_id:
            return False

        trade = await self._load_trade(trade_id)
        if not trade:
            return False
        if (trade.get("mode") or "paper") != "paper":
            return False  # only paper events are emailed by this worker

        user_email = await self._email_for_user(trade.get("user_id"))
        if not user_email:
            await self._mark_emailed(event["id"], reason="no_user_email")
            return False

        # Map raw event_type → renderer-friendly kind
        ev_type = event.get("event_type")
        kind    = "trade_closed" if ev_type == "trade_closed" else "trade_opened"
        rendered = render_trade_email(trade=trade, event_type=kind)

        ok = await self._provider.send(
            to=user_email, subject=rendered.subject,
            html=rendered.html, text=rendered.text,
        )

        if ok:
            await self._mark_emailed(event["id"], reason="sent")
            log.info(
                "email_dispatcher.sent",
                event_id=event["id"], to=user_email, subject=rendered.subject,
            )
        else:
            await self._audit.create({
                "user_id":    trade.get("user_id"),
                "action":     "email_send_failed",
                "record_id":  event["id"],
                "table_name": "trade_events",
                "source":     "autonomous_email_dispatcher",
                "metadata":   {
                    "trade_id": trade_id,
                    "event_type": ev_type,
                    "to_redacted": user_email[:3] + "***",
                    "occurred_at": utcnow_iso(),
                },
            })
        return ok

    async def _load_trade(self, trade_id: str) -> Optional[dict[str, Any]]:
        def _q():
            return (
                self._client.table("trades")
                .select("*")
                .eq("id", trade_id)
                .maybe_single()
                .execute()
            )
        try:
            r = await _run(_q)
        except Exception:
            return None
        return r.data if r and getattr(r, "data", None) else None

    async def _email_for_user(self, user_id: Optional[str]) -> Optional[str]:
        if not user_id:
            return None
        def _get():
            return self._client.auth.admin.get_user_by_id(user_id)
        try:
            res = await _run(_get)
        except Exception:
            return None
        u = getattr(res, "user", None) or (res.get("user") if isinstance(res, dict) else None)
        if not u:
            return None
        return getattr(u, "email", None) or (u.get("email") if isinstance(u, dict) else None)

    async def _mark_emailed(self, event_id: str, *, reason: str) -> None:
        # Read-then-merge metadata, then update.
        def _read():
            return (
                self._client.table("trade_events")
                .select("metadata")
                .eq("id", event_id)
                .maybe_single()
                .execute()
            )
        try:
            r = await _run(_read)
        except Exception:
            return
        meta = (r.data or {}).get("metadata") or {} if r else {}
        meta = {**meta, "emailed_at": utcnow_iso(), "emailed_reason": reason,
                "worker_id": settings.autonomous_worker_id}

        def _upd():
            return (
                self._client.table("trade_events")
                .update({"metadata": meta})
                .eq("id", event_id)
                .execute()
            )
        try:
            await _run(_upd)
        except Exception as exc:
            log.error("email_dispatcher.mark_emailed_failed",
                      event_id=event_id, error=str(exc)[:240])
