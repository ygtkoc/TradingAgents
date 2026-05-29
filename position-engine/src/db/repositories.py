"""
Repository layer — all DB reads and writes for the Position Engine.

Atomic claim protocol (two-phase):
  Phase 1 — fetch_claimable_ids(): SELECT trade IDs (non-locking).
  Phase 2 — claim_for_lifecycle(): UPDATE WHERE lifecycle_status IN ('idle','needs_reconciliation')
             RETURNING *. Returns None if race lost.

Key design rules:
  1. All methods are async (supabase-py runs in asyncio.to_thread).
  2. Raw dicts never escape this layer — callers receive typed models.
  3. service_role key bypasses RLS — no user-level filtering needed here.
  4. NEVER log decrypted API keys or secrets.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Optional

from src.config import settings
from src.db.models import (
    AuditLogInsert,
    Bot,
    ExchangeAccount,
    MarketSnapshot,
    PlatformSettings,
    RiskLogInsert,
    SecurityLogInsert,
    Trade,
    TradeEventInsert,
    TradeUpdateLifecycle,
    UserSettings,
)
from src.db.supabase_client import get_client
from src.logging_config import get_logger
from src.utils.time import utcnow
from src.utils.time import utcnow_iso

log = get_logger(__name__)


async def _run(fn, *args, **kwargs):
    """Run a blocking supabase-py call off the event loop."""
    return await asyncio.to_thread(fn, *args, **kwargs)


def _is_transient_lifecycle_error(error: object) -> bool:
    """Return True for infrastructure errors that should be retried."""
    if not error:
        return False
    text = str(error).lower()
    transient_markers = (
        "server disconnected",
        "connection reset",
        "connection aborted",
        "connection closed",
        "temporarily unavailable",
        "timeout",
        "timed out",
        "network",
        "http/2",
        "httpx",
        "max retries exceeded",
    )
    return any(marker in text for marker in transient_markers)


# ── Trade Lifecycle Repository ─────────────────────────────────────────────────

class TradeLifecycleRepository:
    """
    Two-phase atomic claim for open trades.

    Phase 1: fetch_claimable_ids() — SELECT ids (non-locking).
    Phase 2: claim_for_lifecycle() — UPDATE WHERE lifecycle_status IN ('idle','needs_reconciliation')
             RETURNING *. Atomic. 0 rows → another worker claimed it.
    """

    def __init__(self) -> None:
        self._client = get_client()

    async def fetch_claimable_ids(self, limit: int = 10) -> list[str]:
        """
        Phase 1: SELECT IDs of open trades eligible for lifecycle monitoring.

        Eligible:
          - status IN ('pending', 'open')
          - lifecycle_status IN ('idle', 'needs_reconciliation')

        Non-locking — safe to call concurrently from multiple workers.
        """
        def _select():
            return (
                self._client.table("trades")
                .select("id")
                .in_("status", ["pending", "open"])
                .in_("lifecycle_status", ["idle", "needs_reconciliation"])
                .order("created_at", desc=False)
                .limit(limit)
                .execute()
            )
        result = await _run(_select)
        return [r["id"] for r in (result.data or [])]

    async def release_stale_claims(
        self,
        max_age_minutes: int | None = None,
        max_age_seconds: int | None = None,
    ) -> int:
        """
        Release lifecycle claims left behind by a dead worker.

        Stale monitoring rows are safe to put back to idle. Stale closing rows
        may have submitted a close order, so they are moved to reconciliation
        instead of being retried blindly.
        """
        if settings.dry_run:
            return 0

        if max_age_seconds is not None:
            cutoff = (utcnow() - timedelta(seconds=max_age_seconds)).isoformat()
            age_label = f"{max_age_seconds}s"
        else:
            max_age_minutes = max_age_minutes if max_age_minutes is not None else 10
            cutoff = (utcnow() - timedelta(minutes=max_age_minutes)).isoformat()
            age_label = f"{max_age_minutes}m"

        def _release_monitoring():
            return (
                self._client.table("trades")
                .update({
                    "lifecycle_status":          "idle",
                    "lifecycle_worker_id":       None,
                    "lifecycle_claimed_at":      None,
                    "lifecycle_last_checked_at": utcnow_iso(),
                    "lifecycle_error":           None,
                })
                .in_("status", ["pending", "open"])
                .eq("lifecycle_status", "monitoring")
                .lt("lifecycle_claimed_at", cutoff)
                .execute()
            )

        def _mark_closing_recon():
            return (
                self._client.table("trades")
                .update({
                    "lifecycle_status":          "needs_reconciliation",
                    "lifecycle_worker_id":       None,
                    "lifecycle_claimed_at":      None,
                    "lifecycle_last_checked_at": utcnow_iso(),
                    "lifecycle_error": (
                        "Stale closing claim after worker restart; "
                        "manual reconciliation required"
                    ),
                })
                .eq("status", "open")
                .eq("lifecycle_status", "closing")
                .lt("lifecycle_claimed_at", cutoff)
                .execute()
            )

        monitoring = await _run(_release_monitoring)
        closing = await _run(_mark_closing_recon)
        released = len(monitoring.data or []) + len(closing.data or [])
        if released:
            log.warning(
                "lifecycle.stale_claims_released",
                count=released,
                max_age=age_label,
            )
        return released

    async def recover_transient_failures(self, limit: int = 50) -> int:
        """
        Requeue open trades that failed because of transient infrastructure errors.

        A Supabase/httpx disconnect during P&L update used to leave open trades
        in lifecycle_status='failed'. Failed trades are not claimable, so SL/TP
        monitoring silently stopped. Only known transient error messages are
        recovered here; logic/data failures remain failed for manual inspection.
        """
        if settings.dry_run:
            return 0

        def _select():
            return (
                self._client.table("trades")
                .select("id,lifecycle_error")
                .in_("status", ["pending", "open"])
                .eq("lifecycle_status", "failed")
                .limit(limit)
                .execute()
            )

        result = await _run(_select)
        rows = result.data or []
        recoverable_ids = [
            row["id"]
            for row in rows
            if _is_transient_lifecycle_error(row.get("lifecycle_error"))
        ]
        if not recoverable_ids:
            return 0

        now = utcnow_iso()

        def _update():
            return (
                self._client.table("trades")
                .update({
                    "lifecycle_status":          "idle",
                    "lifecycle_worker_id":       None,
                    "lifecycle_claimed_at":      None,
                    "lifecycle_last_checked_at": now,
                    "lifecycle_error":           None,
                    "lifecycle_retry_count":     0,
                })
                .in_("id", recoverable_ids)
                .eq("lifecycle_status", "failed")
                .in_("status", ["pending", "open"])
                .execute()
            )

        recovered = await _run(_update)
        count = len(recovered.data or [])
        if count:
            log.warning(
                "lifecycle.transient_failures_recovered",
                count=count,
            )
        return count

    async def claim_for_lifecycle(
        self,
        trade_id: str,
        worker_id: str,
    ) -> Optional[Trade]:
        """
        Phase 2: Atomically claim a trade for lifecycle monitoring.

        UPDATE trades
        SET lifecycle_status='monitoring',
            lifecycle_worker_id=worker_id,
            lifecycle_claimed_at=now(),
            lifecycle_last_checked_at=now()
        WHERE id=trade_id
          AND status IN ('pending','open')
          AND lifecycle_status IN ('idle','needs_reconciliation')
        RETURNING *;

        Returns None if 0 rows (race lost — another worker claimed it).
        """
        now = utcnow_iso()

        def _select_current():
            return (
                self._client.table("trades")
                .select("lifecycle_status")
                .eq("id", trade_id)
                .in_("status", ["pending", "open"])
                .in_("lifecycle_status", ["idle", "needs_reconciliation"])
                .limit(1)
                .execute()
            )

        current = await _run(_select_current)
        if not current.data:
            log.debug("lifecycle.claim_missed", trade_id=trade_id, worker=worker_id)
            return None
        original_lifecycle_status = current.data[0]["lifecycle_status"]

        def _update():
            return (
                self._client.table("trades")
                .update({
                    "lifecycle_status":          "monitoring",
                    "lifecycle_worker_id":       worker_id,
                    "lifecycle_claimed_at":      now,
                    "lifecycle_last_checked_at": now,
                })
                .eq("id", trade_id)
                .in_("status", ["pending", "open"])
                .eq("lifecycle_status", original_lifecycle_status)
                .execute()
            )
        result = await _run(_update)
        if not result.data:
            log.debug("lifecycle.claim_missed", trade_id=trade_id, worker=worker_id)
            return None

        trade = Trade.model_validate(result.data[0])
        trade.lifecycle_status = original_lifecycle_status

        # ── Retry limit enforcement ───────────────────────────────────────────
        # The returned row holds the OLD retry count. Increment + check.
        new_retry = (trade.lifecycle_retry_count or 0) + 1
        max_retries = settings.position_max_retries

        if new_retry > max_retries:
            log.error(
                "lifecycle.max_retries_exceeded",
                trade_id=trade_id,
                retry_count=new_retry,
                max_retries=max_retries,
            )
            await self.mark_failed(
                trade_id,
                f"max retries exceeded ({new_retry} > {max_retries})",
            )
            return None  # poller skips this trade

        # Persist the incremented count (best-effort; we already own the claim)
        await self._bump_retry_count(trade_id, new_retry)
        trade.lifecycle_retry_count = new_retry

        log.info(
            "lifecycle.claimed",
            trade_id=trade_id,
            worker=worker_id,
            retry_count=new_retry,
        )
        return trade

    async def _bump_retry_count(self, trade_id: str, new_count: int) -> None:
        """Persist incremented lifecycle_retry_count after a successful claim."""
        if settings.dry_run:
            return

        def _update():
            return (
                self._client.table("trades")
                .update({"lifecycle_retry_count": new_count})
                .eq("id", trade_id)
                .execute()
            )
        try:
            await _run(_update)
        except Exception as exc:
            log.warning(
                "lifecycle.bump_retry_failed",
                trade_id=trade_id,
                error=str(exc)[:200],
            )

    async def release_claim(self, trade_id: str) -> None:
        """
        Release a monitoring claim back to 'idle' (no close action taken).
        Called after UPDATE_PNL, UPDATE_TRAILING_STOP, or HOLD actions.
        """
        if settings.dry_run:
            return

        def _update():
            return (
                self._client.table("trades")
                .update({
                    "lifecycle_status":          "idle",
                    "lifecycle_worker_id":       None,
                    "lifecycle_claimed_at":      None,
                    "lifecycle_last_checked_at": utcnow_iso(),
                    # Reset retry count on a clean release — only stuck/failed
                    # cycles should accumulate retries.
                    "lifecycle_retry_count":     0,
                })
                .eq("id", trade_id)
                .execute()
            )
        await _run(_update)
        log.debug("lifecycle.released", trade_id=trade_id)

    async def update_trade(
        self,
        trade_id: str,
        update: TradeUpdateLifecycle,
    ) -> Optional[Trade]:
        """Apply a lifecycle update to a trade row."""
        if settings.dry_run:
            log.info("dry_run.trade_update", trade_id=trade_id, fields=list(update.to_db_dict()))
            return None

        data = update.to_db_dict()
        if not data:
            return None

        def _update():
            return (
                self._client.table("trades")
                .update(data)
                .eq("id", trade_id)
                .execute()
            )
        result = await _run(_update)
        if result.data:
            return Trade.model_validate(result.data[0])
        return None

    async def mark_closed(
        self,
        trade_id: str,
        *,
        exit_price:     float,
        avg_exit_price: float,
        realized_pnl:   float,
        close_reason:   str,
        close_order_id: Optional[str] = None,
        pnl_pct:        Optional[float] = None,
        r_multiple:     Optional[float] = None,
    ) -> Optional[Trade]:
        """Mark a trade as fully closed."""
        if settings.dry_run:
            log.info("dry_run.trade_close", trade_id=trade_id, reason=close_reason)
            return None

        now = utcnow_iso()

        def _update():
            return (
                self._client.table("trades")
                .update({
                    "status":           "closed",
                    "lifecycle_status": "closed",
                    "lifecycle_worker_id": None,
                    "lifecycle_claimed_at": None,
                    "closed_at":        now,
                    "exit_price":       exit_price,
                    "avg_exit_price":   avg_exit_price,
                    "realized_pnl":     realized_pnl,
                    "pnl_pct":          pnl_pct,
                    "r_multiple":       r_multiple,
                    "unrealized_pnl":   None,
                    "close_reason":     close_reason,
                    "close_order_id":   close_order_id,
                    "lifecycle_last_checked_at": now,
                })
                .eq("id", trade_id)
                .execute()
            )
        result = await _run(_update)
        if result.data:
            trade = Trade.model_validate(result.data[0])
            log.info(
                "trade.closed",
                trade_id=trade_id,
                reason=close_reason,
                realized_pnl=realized_pnl,
            )
            return trade
        return None

    async def mark_needs_reconciliation(
        self,
        trade_id: str,
        reason: str,
    ) -> None:
        """Mark a trade as needing manual reconciliation."""
        if settings.dry_run:
            return

        def _update():
            return (
                self._client.table("trades")
                .update({
                    "lifecycle_status":    "needs_reconciliation",
                    "lifecycle_worker_id": None,
                    "lifecycle_claimed_at": None,
                    "lifecycle_error":     reason[:500],
                    "lifecycle_last_checked_at": utcnow_iso(),
                })
                .eq("id", trade_id)
                .execute()
            )
        await _run(_update)
        log.warning("trade.needs_reconciliation", trade_id=trade_id, reason=reason[:200])

    async def mark_failed(self, trade_id: str, error: str) -> None:
        """Mark lifecycle as permanently failed."""
        if settings.dry_run:
            return

        def _update():
            return (
                self._client.table("trades")
                .update({
                    "lifecycle_status":    "failed",
                    "lifecycle_worker_id": None,
                    "lifecycle_claimed_at": None,
                    "lifecycle_error":     error[:500],
                    "lifecycle_last_checked_at": utcnow_iso(),
                })
                .eq("id", trade_id)
                .execute()
            )
        await _run(_update)
        log.error("lifecycle.marked_failed", trade_id=trade_id, error=error[:200])

    async def get_by_id(self, trade_id: str) -> Optional[Trade]:
        def _select():
            return (
                self._client.table("trades")
                .select("*")
                .eq("id", trade_id)
                .single()
                .execute()
            )
        result = await _run(_select)
        return Trade.model_validate(result.data) if result.data else None

    async def count_critical_security_events(
        self, user_id: str, within_hours: int = 24
    ) -> int:
        from datetime import timedelta
        from src.utils.time import utcnow
        cutoff = (utcnow() - timedelta(hours=within_hours)).isoformat()

        def _count():
            return (
                self._client.table("security_logs")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .eq("severity", "critical")
                .gte("created_at", cutoff)
                .execute()
            )
        result = await _run(_count)
        return result.count or 0


# ── Context Repositories ──────────────────────────────────────────────────────

class ContextRepository:
    """Loads bot, user_settings, and exchange_account for a trade."""

    def __init__(self) -> None:
        self._client = get_client()

    async def get_bot(self, bot_id: str) -> Optional[Bot]:
        def _select():
            return (
                self._client.table("bots")
                .select("*")
                .eq("id", bot_id)
                .single()
                .execute()
            )
        result = await _run(_select)
        return Bot.model_validate(result.data) if result.data else None

    async def get_user_settings(self, user_id: str) -> Optional[UserSettings]:
        def _select():
            return (
                self._client.table("user_settings")
                .select("*")
                .eq("user_id", user_id)
                .single()
                .execute()
            )
        result = await _run(_select)
        return UserSettings.model_validate(result.data) if result.data else None

    async def get_exchange_account(self, account_id: str) -> Optional[ExchangeAccount]:
        def _select():
            return (
                self._client.table("exchange_accounts")
                .select("*")
                .eq("id", account_id)
                .single()
                .execute()
            )
        result = await _run(_select)
        return ExchangeAccount.model_validate(result.data) if result.data else None


# ── Market Data Repository ────────────────────────────────────────────────────

class MarketDataRepository:
    async def get_latest(
        self, exchange: str, symbol: str, timeframe: str = "1h"
    ) -> Optional[MarketSnapshot]:
        def _select():
            return (
                get_client().table("market_snapshots")
                .select("*")
                .eq("exchange", exchange)
                .eq("symbol", symbol)
                .eq("timeframe", timeframe)
                .order("captured_at", desc=True)
                .limit(1)
                .execute()
            )
        result = await _run(_select)
        if result.data:
            return MarketSnapshot.model_validate(result.data[0])
        return None


# ── Platform Settings Repository ─────────────────────────────────────────────

class PlatformSettingsRepository:
    """
    Reads platform_settings rows.
    Called with service_role key — bypasses RLS.

    Cache the result in-process to avoid hitting DB on every lifecycle cycle.
    Cache is invalidated after PLATFORM_SETTINGS_CACHE_TTL_SECONDS.
    """

    def __init__(self) -> None:
        self._client = get_client()
        self._cache: Optional[PlatformSettings] = None
        self._cache_ts: float = 0.0

    async def get(self) -> PlatformSettings:
        import time
        now = time.monotonic()
        if self._cache is not None and (now - self._cache_ts) < settings.platform_settings_cache_ttl_seconds:
            return self._cache

        def _select():
            return (
                self._client.table("platform_settings")
                .select("key, value")
                .execute()
            )
        result = await _run(_select)
        rows = result.data or []
        ps = PlatformSettings.from_rows(rows)
        self._cache = ps
        self._cache_ts = now
        log.debug(
            "platform_settings.loaded",
            global_trading_enabled=ps.global_trading_enabled,
            live_execution_enabled=ps.live_execution_enabled,
            emergency_close_enabled=ps.emergency_close_enabled,
        )
        return ps

    def invalidate(self) -> None:
        self._cache = None
        self._cache_ts = 0.0


# ── Log Repositories ──────────────────────────────────────────────────────────

class TradeEventRepository:
    async def create(self, event: TradeEventInsert) -> None:
        if settings.dry_run:
            log.debug("dry_run.trade_event", event_type=event.event_type)
            return

        def _insert():
            return get_client().table("trade_events").insert(event.model_dump()).execute()

        await _run(_insert)

    async def bulk_create(self, events: list[TradeEventInsert]) -> None:
        if settings.dry_run or not events:
            return
        rows = [e.model_dump() for e in events]

        def _insert():
            return get_client().table("trade_events").insert(rows).execute()

        await _run(_insert)


class RiskLogRepository:
    async def create(self, entry: RiskLogInsert) -> None:
        if settings.dry_run:
            return

        def _insert():
            return get_client().table("risk_logs").insert(entry.model_dump()).execute()

        await _run(_insert)


class SecurityLogRepository:
    async def create(self, entry: SecurityLogInsert) -> None:
        if settings.dry_run:
            return

        def _insert():
            return get_client().table("security_logs").insert(entry.model_dump()).execute()

        await _run(_insert)


class AuditLogRepository:
    async def create(self, entry: AuditLogInsert) -> None:
        if settings.dry_run:
            return

        def _insert():
            return get_client().table("audit_logs").insert(entry.model_dump()).execute()

        await _run(_insert)
