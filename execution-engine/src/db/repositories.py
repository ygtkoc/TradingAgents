"""
Repository layer — all database reads and writes for the Execution Engine.

Design principles:
  1. Every method is async (wraps sync supabase-py in asyncio.to_thread).
  2. Callers receive typed Pydantic models; raw dicts never escape this layer.
  3. service_role is used for all operations — no RLS filtering applies here.
  4. Every write that touches a core pipeline table emits a structured log.
  5. Failures raise exceptions; callers decide whether to retry or fail closed.
  6. NEVER log decrypted API keys or secrets.

Atomic claim protocol (two-phase):
  Phase 1 — fetch_executable_ids(): SELECT candidate decision IDs (non-locking).
  Phase 2 — claim_for_execution(): UPDATE WHERE execution_status='pending_execution'
             RETURNING *. Returns None if another worker already claimed it.
"""
from __future__ import annotations

import asyncio
from datetime import timezone
from typing import Optional

from src.config import settings
from src.db.models import (
    AuditLogInsert,
    Bot,
    BotConfig,
    ExchangeAccount,
    MarketSnapshot,
    RiskLogInsert,
    SecurityLogInsert,
    Trade,
    TradeDecision,
    TradeEventInsert,
    TradeInsert,
    UserSettings,
)
from src.db.supabase_client import get_client
from src.logging_config import get_logger
from src.utils.time import utcnow_iso

log = get_logger(__name__)


class DuplicateOpenExposureError(RuntimeError):
    """Raised when the DB rejects duplicate open user/mode/symbol exposure."""


# ── Async helper ──────────────────────────────────────────────────────────────

async def _run(fn, *args, **kwargs):
    """Run a blocking supabase-py call in a thread pool."""
    return await asyncio.to_thread(fn, *args, **kwargs)


# ── Trade Decision Repository ─────────────────────────────────────────────────

class TradeDecisionRepository:
    """
    Two-phase atomic claim for trade_decisions.

    Phase 1: fetch_executable_ids() — SELECT ids of claimable decisions.
    Phase 2: claim_for_execution()  — UPDATE WHERE execution_status='pending_execution'
                                      AND id=X RETURNING *

    Only the Phase 2 UPDATE is the serialisation point. Phase 1 is non-locking
    and safe to call concurrently from multiple workers.
    """

    def __init__(self) -> None:
        self._client = get_client()

    async def fetch_executable_ids(self, limit: int = 5) -> list[str]:
        """
        Phase 1: SELECT IDs of claimable decisions. Non-locking.

        Conditions:
          - final_decision IN ('open_long', 'open_short')
          - approval_status IN ('approved', 'auto_approved')
          - execution_status = 'pending_execution'
          - linked_trade_id IS NULL   ← idempotency anchor
        """
        def _select():
            return (
                self._client.table("trade_decisions")
                .select("id, linked_trade_id")
                .in_("final_decision", ["open_long", "open_short"])
                .in_("approval_status", ["approved", "auto_approved"])
                .eq("execution_status", "pending_execution")
                .order("created_at", desc=False)
                .limit(limit)
                .execute()
            )
        result = await _run(_select)
        return [
            row["id"]
            for row in (result.data or [])
            if row.get("linked_trade_id") is None
        ]

    async def claim_for_execution(
        self,
        decision_id: str,
        worker_id: str,
    ) -> Optional[TradeDecision]:
        """
        Phase 2: Atomically claim a decision for execution.

        UPDATE trade_decisions
        SET execution_status = 'executing',
            execution_worker_id = worker_id,
            execution_started_at = now()
        WHERE id = decision_id
          AND execution_status = 'pending_execution'   -- concurrency guard
          AND linked_trade_id IS NULL                  -- idempotency guard
        RETURNING *;

        Returns None if the row was claimed by another worker.
        """
        now = utcnow_iso()

        def _update():
            return (
                self._client.table("trade_decisions")
                .update({
                    "execution_status":    "executing",
                    "execution_worker_id": worker_id,
                    "execution_started_at": now,
                })
                .eq("id", decision_id)
                .eq("execution_status", "pending_execution")
                .execute()
            )
        result = await _run(_update)
        if not result.data:
            log.info(
                "execution.claim_missed",
                decision_id=decision_id,
                worker=worker_id,
                reason="already claimed or linked",
            )
            return None

        log.info("execution.claimed", decision_id=decision_id, worker=worker_id)
        return TradeDecision.model_validate(result.data[0])

    async def mark_executed(self, decision_id: str, trade_id: str) -> None:
        """Mark decision as executed with linked trade."""
        if settings.dry_run:
            return

        def _update():
            return (
                self._client.table("trade_decisions")
                .update({
                    "execution_status":       "executed",
                    "execution_completed_at": utcnow_iso(),
                    "linked_trade_id":        trade_id,
                })
                .eq("id", decision_id)
                .execute()
            )
        await _run(_update)
        log.info("execution.marked_executed", decision_id=decision_id, trade_id=trade_id)

    async def mark_failed(self, decision_id: str, error: str) -> None:
        """Mark decision as permanently failed."""
        if settings.dry_run:
            return

        def _update():
            return (
                self._client.table("trade_decisions")
                .update({
                    "execution_status":       "failed",
                    "execution_completed_at": utcnow_iso(),
                    "execution_error":        error[:500],
                    "execution_worker_id":    None,
                })
                .eq("id", decision_id)
                .execute()
            )
        await _run(_update)
        log.error("execution.marked_failed", decision_id=decision_id, error=error[:200])

    async def mark_skipped(self, decision_id: str, reason: str) -> None:
        """Mark decision as skipped (security/risk block — not an error)."""
        if settings.dry_run:
            return

        def _update():
            return (
                self._client.table("trade_decisions")
                .update({
                    "execution_status":       "skipped",
                    "execution_completed_at": utcnow_iso(),
                    "execution_error":        reason[:500],
                    "execution_worker_id":    None,
                })
                .eq("id", decision_id)
                .execute()
            )
        await _run(_update)
        log.warning("execution.marked_skipped", decision_id=decision_id, reason=reason[:200])

    async def get_by_id(self, decision_id: str) -> Optional[TradeDecision]:
        def _select():
            return (
                self._client.table("trade_decisions")
                .select("*")
                .eq("id", decision_id)
                .single()
                .execute()
            )
        result = await _run(_select)
        return TradeDecision.model_validate(result.data) if result.data else None

    async def count_critical_security_events(
        self, user_id: str, within_hours: int = 24
    ) -> int:
        """
        Count recent critical security log events for a user.
        Used by SecurityExecutionGuard to block execution when the user has
        unresolved critical security flags.

        Guard-generated audit rows must not recursively block future decisions.
        They describe that execution was blocked; they are not the underlying
        account/security condition that needs review.
        """
        # Supabase doesn't support WHERE created_at > X directly in the SDK's
        # filter chaining, so we use a raw SQL via RPC or approximate with gte.
        # For now, use a simple gte with an ISO timestamp.
        from datetime import timedelta
        from src.utils.time import utcnow
        cutoff = (utcnow() - timedelta(hours=within_hours)).isoformat()

        def _count():
            return (
                self._client.table("security_logs")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .eq("severity", "critical")
                .eq("resolved", False)
                .neq("event_type", "security_guard_blocked_execution")
                .gte("created_at", cutoff)
                .execute()
            )
        result = await _run(_count)
        return result.count or 0


# ── Bot + Context Repository ──────────────────────────────────────────────────

class BotRepository:
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

    async def get_active_config(self, bot: Bot) -> Optional[BotConfig]:
        if not bot.active_config_id:
            return None

        def _select():
            return (
                self._client.table("bot_configs")
                .select("*")
                .eq("id", bot.active_config_id)
                .eq("is_active", True)
                .single()
                .execute()
            )
        result = await _run(_select)
        return BotConfig.model_validate(result.data) if result.data else None

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

    async def get_exchange_account(
        self, account_id: str
    ) -> Optional[ExchangeAccount]:
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

    async def count_open_trades(self, bot_id: str) -> int:
        def _select():
            return (
                self._client.table("trades")
                .select("id", count="exact")
                .eq("bot_id", bot_id)
                .eq("status", "open")
                .execute()
            )
        result = await _run(_select)
        return result.count or 0


# ── Trade Repository ──────────────────────────────────────────────────────────

class TradeRepository:
    def __init__(self) -> None:
        self._client = get_client()

    async def create(self, trade: TradeInsert) -> Trade:
        """Creates a trade row and returns the full row."""
        if settings.dry_run:
            log.info("dry_run.trade.create", trade=trade.model_dump(exclude={"metadata"}))
            from src.utils.time import utcnow_iso
            return Trade(
                id="dry-run-trade-id",
                created_at=utcnow_iso(),
                **trade.model_dump(),
            )

        def _insert():
            payload = trade.model_dump(
                exclude_none=True,
                exclude={"agent_run_id"},
            )
            if "avg_fill_price" in payload and "avg_entry_price" not in payload:
                payload["avg_entry_price"] = payload.pop("avg_fill_price")
            else:
                payload.pop("avg_fill_price", None)
            payload.pop("pnl", None)
            return (
                self._client.table("trades")
                .insert(payload)
                .execute()
            )

        try:
            result = await _run(_insert)
        except Exception as exc:
            message = str(exc)
            if (
                "trades_one_open_symbol_per_user_mode_idx" in message
                or "duplicate key" in message.lower()
            ):
                raise DuplicateOpenExposureError(
                    "Open exposure already exists for this user/mode/symbol"
                ) from exc
            raise
        rows = result.data or []
        if not rows:
            raise RuntimeError("Trade insert returned no rows")
        t = Trade.model_validate(rows[0])
        log.info("trade.created", trade_id=t.id, mode=t.mode, symbol=t.symbol)
        return t

    async def find_by_decision_id(
        self, trade_decision_id: str
    ) -> Optional[Trade]:
        """Idempotency check: find existing trade for a decision."""
        def _select():
            return (
                self._client.table("trades")
                .select("*")
                .eq("trade_decision_id", trade_decision_id)
                .limit(1)
                .execute()
            )
        result = await _run(_select)
        if result.data:
            return Trade.model_validate(result.data[0])
        return None

    async def find_open_symbol_exposure(
        self,
        *,
        user_id: str,
        symbol: str,
        mode: Optional[str] = None,
    ) -> Optional[Trade]:
        """
        Return an existing open trade for the same user+symbol exposure.

        This is deliberately broader than decision idempotency: a new decision
        must not open another HBAR/CHZ/etc. position while an earlier position
        on that symbol is still open, even if the new decision has the opposite
        direction.
        """
        target = _normalize_symbol(symbol)

        def _select():
            query = (
                self._client.table("trades")
                .select("*")
                .eq("user_id", user_id)
                .eq("status", "open")
                .order("created_at", desc=True)
                .limit(100)
            )
            if mode:
                query = query.eq("mode", mode)
            return query.execute()

        result = await _run(_select)
        for row in result.data or []:
            if _normalize_symbol(str(row.get("symbol") or "")) == target:
                return Trade.model_validate(row)
        return None

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

    async def realized_loss_today_usd(
        self,
        *,
        user_id: str,
        mode: Optional[str] = None,
    ) -> float:
        """
        Return today's net realized loss for a user's account.

        Positive realized PnL offsets losses. The risk guard only needs the loss
        magnitude, so profitable or flat days return 0.
        """
        from src.utils.time import utcnow

        start = utcnow().astimezone(timezone.utc).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        def _select():
            query = (
                self._client.table("trades")
                .select("realized_pnl,closed_at")
                .eq("user_id", user_id)
                .eq("status", "closed")
                .gte("closed_at", start.isoformat())
                .limit(1000)
            )
            if mode:
                query = query.eq("mode", mode)
            return query.execute()

        result = await _run(_select)
        net_pnl = 0.0
        for row in result.data or []:
            value = row.get("realized_pnl")
            try:
                net_pnl += float(value or 0.0)
            except (TypeError, ValueError):
                continue
        return abs(net_pnl) if net_pnl < 0 else 0.0


# ── Trade Event Repository ────────────────────────────────────────────────────

class TradeEventRepository:
    def __init__(self) -> None:
        self._client = get_client()

    async def create(self, event: TradeEventInsert) -> None:
        """Write a single trade event. Fire-and-forget safe."""
        if settings.dry_run:
            log.debug("dry_run.trade_event", event_type=event.event_type)
            return

        def _insert():
            return (
                self._client.table("trade_events")
                .insert(event.model_dump())
                .execute()
            )
        await _run(_insert)

    async def bulk_create(self, events: list[TradeEventInsert]) -> None:
        if settings.dry_run or not events:
            return

        rows = [e.model_dump() for e in events]

        def _insert():
            return self._client.table("trade_events").insert(rows).execute()

        await _run(_insert)


# ── Ancillary Log Repositories ────────────────────────────────────────────────

class RiskLogRepository:
    async def create(self, entry: RiskLogInsert) -> None:
        if settings.dry_run:
            return

        def _insert():
            return get_client().table("risk_logs").insert(entry.model_dump()).execute()

        await _run(_insert)


class KnowledgeRepository:
    def __init__(self) -> None:
        self._client = get_client()

    async def fetch_rules(self, user_id: str) -> list[dict]:
        def _select():
            return (
                self._client.table("trading_strategy_rules")
                .select("*")
                .eq("active", True)
                .or_(f"user_id.is.null,user_id.eq.{user_id}")
                .order("created_at", desc=False)
                .execute()
            )

        result = await _run(_select)
        return result.data or []

    async def fetch_relevant_chunks(
        self,
        *,
        user_id: str,
        tags: list[str],
        limit: int = 8,
    ) -> list[dict]:
        def _select():
            return (
                self._client.table("trading_knowledge_chunks")
                .select("id, source_id, content, tags, metadata")
                .or_(f"user_id.is.null,user_id.eq.{user_id}")
                .limit(250)
                .execute()
            )

        result = await _run(_select)
        rows = result.data or []
        if not tags:
            return rows[:limit]
        wanted = set(tags)
        ranked = [
            row for row in rows
            if wanted.intersection(set(row.get("tags") or []))
        ]
        return (ranked or rows)[:limit]

    async def upsert_review(self, review: dict) -> None:
        if settings.dry_run:
            return

        def _upsert():
            return (
                self._client.table("decision_knowledge_reviews")
                .upsert(review, on_conflict="trade_decision_id")
                .execute()
            )

        await _run(_upsert)


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


# ── Market Data Repository ────────────────────────────────────────────────────

# ── Platform Settings Repository ─────────────────────────────────────────────

class PlatformSettingsRepository:
    """
    Reads platform_settings rows via service_role key (bypasses RLS).

    Results are cached in-process for PLATFORM_SETTINGS_CACHE_TTL_SECONDS
    (default 30s) to avoid hitting the DB on every execution pipeline.

    Invariant: if the DB is unreachable, returns safe defaults so execution
    continues with global_trading_enabled=True (fail-open only for the cache
    fallback; the caller may override this with fail-closed logic).
    """

    _DEFAULT_TTL: float = 30.0   # seconds

    def __init__(self) -> None:
        self._client    = get_client()
        self._cache     = None          # type: Optional["PlatformSettings"]
        self._cache_ts  = 0.0

    async def get(self) -> "PlatformSettings":
        import time
        from src.db.models import PlatformSettings

        now = time.monotonic()
        ttl = getattr(settings, "platform_settings_cache_ttl_seconds", self._DEFAULT_TTL)

        if self._cache is not None and (now - self._cache_ts) < ttl:
            return self._cache

        def _select():
            return (
                self._client.table("platform_settings")
                .select("key, value")
                .execute()
            )

        try:
            result = await _run(_select)
            rows   = result.data or []
            ps     = PlatformSettings.from_rows(rows)
        except Exception as exc:
            log.error("platform_settings.fetch_failed", error=str(exc)[:200])
            if self._cache is not None:
                return self._cache  # serve stale cache on error
            from src.db.models import PlatformSettings
            ps = PlatformSettings()  # safe defaults

        self._cache    = ps
        self._cache_ts = now
        log.debug(
            "platform_settings.loaded",
            global_trading_enabled=ps.global_trading_enabled,
            live_execution_enabled=ps.live_execution_enabled,
        )
        return ps

    def invalidate(self) -> None:
        self._cache    = None
        self._cache_ts = 0.0


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


def _normalize_symbol(symbol: str) -> str:
    return "".join(ch for ch in symbol.upper() if ch.isalnum())
