"""
Repository layer — all database reads and writes for the agent engine.

Design principles:
  1. Every method is async (wraps sync supabase-py in asyncio.to_thread).
  2. Callers receive typed Pydantic models; raw dicts never escape this layer.
  3. service_role is used for all operations — no RLS filtering applies here.
     Ownership checks must be done by the caller if relevant.
  4. Every write that touches a core pipeline table emits a structured log entry.
  5. Failures raise exceptions; callers decide whether to retry or fail closed.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from src.config import settings
from src.db.models import (
    AgentDecision,
    AgentOutputResult,
    AgentDefinition,
    AgentOutputInsert,
    AgentRunInsert,
    AuditLogInsert,
    Bot,
    BotConfig,
    ExchangeAccount,
    MarketSnapshot,
    RiskLogInsert,
    SecurityLogInsert,
    Signal,
    SignalStatus,
    SystemEvolutionReportInsert,
    TradeDecisionInsert,
    UserSettings,
)
from src.db.supabase_client import execute_with_retry, get_client
from src.logging_config import get_logger
from src.utils.time import utcnow_iso

log = get_logger(__name__)


# ── Async helpers ─────────────────────────────────────────────────────────────

async def _run(fn, *args, **kwargs):
    """Run a blocking supabase-py READ call in a thread pool (no retry)."""
    return await asyncio.to_thread(fn, *args, **kwargs)


async def _write(fn):
    """Run a blocking supabase-py WRITE call with transparent retry.

    Wraps `execute_with_retry` in a thread so it can be awaited from async
    code. The retry loop resets the client singleton on transient connection
    errors (HTTP/2 disconnect, ECONNRESET) and backs off exponentially before
    each attempt (1 s → 3 s → 8 s, max 3 attempts).

    On exhaustion the error is logged as `db.write.failed` and re-raised so
    the caller decides whether to propagate or swallow.
    """
    return await asyncio.to_thread(execute_with_retry, fn)


# ── Signal repository ─────────────────────────────────────────────────────────

class SignalRepository:
    """
    Signal table access.

    Claim protocol (two-phase atomic):
      Phase 1 — fetch_pending_ids(): SELECT ids of unclaimed pending signals (non-locking).
      Phase 2 — claim_by_id():       UPDATE WHERE id=X AND status='pending' RETURNING *.
                                     If 0 rows returned → claimed by other worker → skip.

    This is safer than a combined SELECT+UPDATE because:
    - Phase 1 never holds a lock; any number of workers can read concurrently.
    - Phase 2 is the only serialisation point; Postgres UPDATE is atomic.
    - Race condition is fully handled at the DB level, not in Python.

    Failure behaviour:
    - Permanent failures (injection detected, invalid signal, bot not found):
      mark_permanently_failed() → status='failed', not retried.
    - Transient failures (pipeline error, timeout):
      Leave status as 'processing'. The release_stuck_signals() DB function
      (called by pg_cron every 5 minutes) resets them to 'pending' after timeout.
      This avoids retry storm loops — the 5-minute gate enforces a minimum retry gap.
    """

    def __init__(self) -> None:
        self._client = get_client()

    async def fetch_pending_ids(self, limit: int = 10) -> list[str]:
        """
        Phase 1: Returns up to `limit` IDs of unclaimed pending signals.

        Non-locking — multiple workers can call this simultaneously.
        Each worker then races to claim individual IDs in Phase 2.
        """
        def _select():
            return (
                self._client.table("signals")
                .select("id")
                .eq("status", "pending")
                .is_("processing_worker_id", "null")
                .order("created_at", desc=False)
                .limit(limit)
                .execute()
            )
        result = await _run(_select)
        return [r["id"] for r in (result.data or [])]

    async def claim_by_id(self, signal_id: str, worker_id: str) -> Optional[Signal]:
        """
        Phase 2: Atomically claim a specific signal by id.

        Executes:
            UPDATE signals
            SET status = 'processing',
                processing_worker_id = worker_id,
                processing_started_at = now()
            WHERE id = signal_id
              AND status = 'pending'
            RETURNING *;

        Returns:
            The claimed Signal if successful, None if another worker already claimed it.
        """
        now = utcnow_iso()

        def _update():
            return (
                self._client.table("signals")
                .update({
                    "status": "processing",
                    "processing_worker_id": worker_id,
                    "processing_started_at": now,
                })
                .eq("id", signal_id)
                .eq("status", "pending")   # Atomic concurrency guard
                .execute()
            )

        result = await _write(_update)

        if not result.data:
            log.info(
                "signal.claim_missed",
                signal_id=signal_id,
                worker=worker_id,
                reason="status no longer pending",
            )
            return None

        log.info("signal.claimed", signal_id=signal_id, worker=worker_id)
        return Signal.model_validate(result.data[0])

    async def mark_processed(self, signal_id: str) -> None:
        """
        Marks a signal as successfully processed.
        Sets status='processed' and processed_at=now().
        Retains processing_worker_id for audit trail.
        """
        now = utcnow_iso()

        def _update():
            return (
                self._client.table("signals")
                .update({
                    "status": "processed",
                    "processed_at": now,
                })
                .eq("id", signal_id)
                .execute()
            )
        await _write(_update)
        log.info("signal.processed", signal_id=signal_id)

    async def mark_permanently_failed(self, signal_id: str, error: str) -> None:
        """
        Marks a signal as permanently failed (will NOT be retried).

        Use for: invalid signal data, security vetoes, injection detected,
        missing required context. Do NOT use for transient pipeline errors
        (those are handled by release_stuck_signals()).
        """
        def _update():
            return (
                self._client.table("signals")
                .update({
                    "status": "failed",
                    "processing_worker_id": None,
                    "processing_started_at": None,
                    "metadata": {"permanent_failure_reason": error[:500]},
                })
                .eq("id", signal_id)
                .execute()
            )
        await _write(_update)
        log.error(
            "signal.permanently_failed",
            signal_id=signal_id,
            error=error[:300],
        )

    async def mark_failed(self, signal_id: str, error: str) -> None:
        """Marks a signal failed and clears worker ownership immediately."""
        def _update():
            return (
                self._client.table("signals")
                .update({
                    "status": SignalStatus.FAILED.value,
                    "processing_worker_id": None,
                    "processing_started_at": None,
                    "metadata": {"pipeline_failure_reason": error[:500]},
                })
                .eq("id", signal_id)
                .execute()
            )
        await _write(_update)
        log.error("signal.failed", signal_id=signal_id, error=error[:300])

    async def get_by_id(self, signal_id: str) -> Optional[Signal]:
        def _select():
            return (
                self._client.table("signals")
                .select("*")
                .eq("id", signal_id)
                .single()
                .execute()
            )
        result = await _run(_select)
        return Signal.model_validate(result.data) if result.data else None


# ── Bot + config repository ───────────────────────────────────────────────────

class BotRepository:
    async def get_bot(self, bot_id: str) -> Optional[Bot]:
        def _select():
            return (
                get_client().table("bots")
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
                get_client().table("bot_configs")
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
                get_client().table("user_settings")
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
                get_client().table("exchange_accounts")
                .select("*")
                .eq("id", account_id)
                .single()
                .execute()
            )
        result = await _run(_select)
        return ExchangeAccount.model_validate(result.data) if result.data else None

    async def count_open_trades(
        self,
        bot_id: str,
        user_id: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> int:
        """Count truly active positions: status in (open, partially_filled).

        Only trades with statuses that represent real capital at risk are
        counted. Closed, cancelled, failed, or reset trades are excluded.

        Args:
            bot_id:  Required — the bot whose positions are counted.
            user_id: Optional defense-in-depth filter.
            mode:    Optional mode filter ('paper' | 'live' | 'shadow').
        """
        def _select():
            q = (
                get_client().table("trades")
                .select("id, status, mode, symbol")
                # Count only trades that hold open risk
                .in_("status", ["open", "partially_filled"])
                .eq("bot_id", bot_id)
            )
            if user_id:
                q = q.eq("user_id", user_id)
            if mode:
                q = q.eq("mode", mode)
            return q.execute()

        result = await _run(_select)
        rows = result.data or []
        count = len(rows)

        log.info(
            "portfolio.open_positions.count",
            bot_id=bot_id,
            user_id=user_id,
            mode=mode,
            count=count,
        )
        if count > 0:
            log.info(
                "portfolio.trade_ids",
                bot_id=bot_id,
                trade_ids=[r["id"] for r in rows],
                statuses=[r.get("status") for r in rows],
                modes=[r.get("mode") for r in rows],
            )
        return count

    async def update_signal_timestamps(
        self,
        bot_id: str,
        last_signal_at: "datetime",
        next_signal_at: "datetime",
    ) -> None:
        """Persist last/next signal timestamps after the signal generator seeds a signal."""
        def _update():
            return (
                get_client().table("bots")
                .update({
                    "last_signal_at": last_signal_at.isoformat(),
                    "next_signal_at": next_signal_at.isoformat(),
                })
                .eq("id", bot_id)
                .execute()
            )
        await _write(_update)

    async def update_warmup_status(
        self,
        bot_id: str,
        warmup_status: str,
        candles_collected: int,
        *,
        warmup_started_at: Optional["datetime"] = None,
        warmup_completed_at: Optional["datetime"] = None,
    ) -> None:
        """Update bot warmup progress (called by the autonomous signal generator)."""
        payload: dict = {
            "warmup_status":     warmup_status,
            "candles_collected": candles_collected,
        }
        if warmup_started_at is not None:
            payload["warmup_started_at"] = warmup_started_at.isoformat()
        if warmup_completed_at is not None:
            payload["warmup_completed_at"] = warmup_completed_at.isoformat()

        def _update():
            return (
                get_client().table("bots")
                .update(payload)
                .eq("id", bot_id)
                .execute()
            )
        await _write(_update)
        log.info(
            "warmup.status_updated",
            bot_id=bot_id,
            warmup_status=warmup_status,
            candles_collected=candles_collected,
        )


# ── Agent definition repository ───────────────────────────────────────────────

class AgentDefinitionRepository:
    async def get_enabled(self) -> list[AgentDefinition]:
        def _select():
            return (
                get_client().table("agent_definitions")
                .select("*")
                .eq("enabled", True)
                .order("category")
                .execute()
            )
        result = await _run(_select)
        return [AgentDefinition.model_validate(r) for r in (result.data or [])]

    async def get_by_name(self, name: str) -> Optional[AgentDefinition]:
        def _select():
            return (
                get_client().table("agent_definitions")
                .select("*")
                .eq("name", name)
                .single()
                .execute()
            )
        result = await _run(_select)
        return AgentDefinition.model_validate(result.data) if result.data else None


# ── Market snapshot repository ────────────────────────────────────────────────

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
        if not result.data:
            return None
        return MarketSnapshot.model_validate(result.data[0])

    async def get_history(
        self, exchange: str, symbol: str, timeframe: str, limit: int = 50
    ) -> list[MarketSnapshot]:
        def _select():
            return (
                get_client().table("market_snapshots")
                .select("*")
                .eq("exchange", exchange)
                .eq("symbol", symbol)
                .eq("timeframe", timeframe)
                .order("captured_at", desc=True)
                .limit(limit)
                .execute()
            )
        result = await _run(_select)
        return [MarketSnapshot.model_validate(r) for r in (result.data or [])]


# ── Agent run repository ──────────────────────────────────────────────────────

class AgentRunRepository:
    async def create(self, run: AgentRunInsert) -> str:
        """Creates an agent_run row and returns its id.

        NOTE: supabase-py does not support `.select(...)` chained after
        `.insert(...)`. The inserted rows come back via `result.data` by
        default (PostgREST `Prefer: return=representation`).
        """
        if settings.dry_run:
            log.debug("dry_run.agent_run.create", run=run.model_dump())
            return "dry-run-agent-run-id"

        def _insert():
            return (
                get_client().table("agent_runs")
                .insert(run.model_dump())
                .execute()
            )
        result = await _write(_insert)
        if not result.data:
            raise RuntimeError("agent_runs insert returned no rows")
        run_id = result.data[0]["id"]
        log.debug("agent_run.created", run_id=run_id)
        return run_id

    async def update_status(
        self,
        run_id: str,
        status: str,
        completed_at: Optional[str] = None,
        duration_ms: Optional[int] = None,
        final_summary: Optional[dict] = None,
        error_message: Optional[str] = None,
        trade_decision_id: Optional[str] = None,
    ) -> None:
        if settings.dry_run:
            return

        payload: dict = {"run_status": status}
        if completed_at:
            payload["completed_at"] = completed_at
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        if final_summary is not None:
            payload["final_summary"] = final_summary
        if error_message:
            payload["error_message"] = error_message[:2000]
        if trade_decision_id:
            payload["trade_decision_id"] = trade_decision_id

        def _update():
            return (
                get_client().table("agent_runs")
                .update(payload)
                .eq("id", run_id)
                .execute()
            )
        await _write(_update)


# ── Agent output repository ───────────────────────────────────────────────────

class AgentOutputRepository:
    async def bulk_create(self, outputs: list[AgentOutputInsert]) -> None:
        """Inserts all agent outputs in a single batch request."""
        if settings.dry_run or not outputs:
            return

        rows = [o.model_dump() for o in outputs]

        def _insert():
            return get_client().table("agent_outputs").insert(rows).execute()

        await _write(_insert)
        log.debug("agent_outputs.bulk_created", count=len(outputs))


# ── Trade decision repository ─────────────────────────────────────────────────

class TradeDecisionRepository:
    async def create(self, decision: TradeDecisionInsert) -> str:
        """Inserts a trade_decision and returns its id."""
        if settings.dry_run:
            log.info(
                "dry_run.trade_decision",
                decision=decision.final_decision,
                symbol=decision.symbol,
                score=decision.score_summary.get("final_score"),
            )
            return "dry-run-trade-decision-id"

        def _insert():
            return (
                get_client().table("trade_decisions")
                .insert(decision.model_dump())
                .execute()
            )
        result = await _write(_insert)
        if not result.data:
            raise RuntimeError("trade_decisions insert returned no rows")
        decision_id = result.data[0]["id"]
        log.info(
            "trade_decision.created",
            decision_id=decision_id,
            final_decision=decision.final_decision,
            symbol=decision.symbol,
            approval_status=decision.approval_status,
            execution_status=decision.execution_status,
        )
        return decision_id


# ── Paper execution repository ────────────────────────────────────────────────

class PaperExecutionRepository:
    """Creates trades and paper_account_events for auto-approved paper decisions.

    This is the minimal execution engine for paper mode. It:
      1. Claims the trade_decision (execution_status → executing).
      2. Reads the paper_accounts balance for the user.
      3. Computes position sizing using the 2% risk rule.
      4. Inserts a trades row (status='open').
      5. Inserts a paper_account_events debit (balance reservation).
      6. Updates paper_accounts.balance.
      7. Marks trade_decision as executed (linked_trade_id set).

    Every step uses service_role and bypasses RLS.
    """

    async def claim_decision(self, decision_id: str, worker_id: str) -> bool:
        """Atomically claim a trade_decision for execution.

        Returns True if claimed successfully, False if already taken.
        """
        def _update():
            return (
                get_client().table("trade_decisions")
                .update({
                    "execution_status":    "executing",
                    "execution_worker_id": worker_id,
                    "execution_started_at": __import__("src.utils.time", fromlist=["utcnow_iso"]).utcnow_iso(),
                })
                .eq("id", decision_id)
                .eq("execution_status", "pending_execution")
                .execute()
            )
        result = await _write(_update)
        return bool(result.data)

    async def get_paper_balance(self, user_id: str) -> Optional[dict]:
        """Returns the paper_accounts row (id, balance, status) for the user."""
        def _select():
            return (
                get_client().table("paper_accounts")
                .select("id, balance, status, starting_balance, realized_pnl, unrealized_pnl")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
        result = await _run(_select)
        return result.data if result else None

    async def insert_trade(self, row: dict) -> str:
        """Insert a trades row and return its id."""
        def _insert():
            return get_client().table("trades").insert(row).execute()
        result = await _write(_insert)
        if not result.data:
            raise RuntimeError("trades insert returned no rows")
        return result.data[0]["id"]

    async def insert_paper_event(self, row: dict) -> str:
        """Insert a paper_account_events row and return its id."""
        def _insert():
            return get_client().table("paper_account_events").insert(row).execute()
        result = await _write(_insert)
        if not result.data:
            raise RuntimeError("paper_account_events insert returned no rows")
        return result.data[0]["id"]

    async def debit_paper_balance(
        self,
        account_id: str,
        user_id: str,
        risk_amount: float,
        new_balance: float,
    ) -> None:
        """Reserve risk capital by updating paper_accounts.balance."""
        def _update():
            return (
                get_client().table("paper_accounts")
                .update({
                    "balance": new_balance,
                    "unrealized_pnl": 0.0,   # reset per-trade; updated by position engine later
                })
                .eq("id", account_id)
                .eq("user_id", user_id)
                .execute()
            )
        await _write(_update)

    async def mark_decision_executed(
        self,
        decision_id: str,
        trade_id: str,
        worker_id: str,
    ) -> None:
        """Mark trade_decision as executed and link to the trade row."""
        from src.utils.time import utcnow_iso
        def _update():
            return (
                get_client().table("trade_decisions")
                .update({
                    "execution_status":      "executed",
                    "execution_completed_at": utcnow_iso(),
                    "execution_worker_id":   worker_id,
                    "linked_trade_id":       trade_id,
                })
                .eq("id", decision_id)
                .execute()
            )
        await _write(_update)

    async def mark_decision_failed(
        self,
        decision_id: str,
        error: str,
        worker_id: str,
    ) -> None:
        """Mark trade_decision execution as failed."""
        from src.utils.time import utcnow_iso
        def _update():
            return (
                get_client().table("trade_decisions")
                .update({
                    "execution_status":       "failed",
                    "execution_completed_at":  utcnow_iso(),
                    "execution_worker_id":    worker_id,
                    "execution_error":        error[:1000],
                })
                .eq("id", decision_id)
                .execute()
            )
        await _write(_update)

    async def insert_trade_event(self, row: dict) -> None:
        """Append a trade_events audit row."""
        def _insert():
            return get_client().table("trade_events").insert(row).execute()
        try:
            await _write(_insert)
        except Exception:
            pass  # trade_events are best-effort audit records


def build_failed_agent_output(
    *,
    agent_name: str,
    agent_definition_id: str,
    agent_category: str,
    error: str,
) -> AgentOutputResult:
    return AgentOutputResult(
        agent_name=agent_name,
        agent_definition_id=agent_definition_id,
        agent_category=agent_category,
        decision=AgentDecision.WAIT,
        score=0.0,
        confidence=0.0,
        veto=False,
        reasoning=f"Agent failure: {error[:200]}",
        output={"error": error[:200]},
        risk_flags=["agent_error"],
        security_flags=[],
        recommendations=["Investigate agent pipeline failure"],
        error=error[:500],
    )


# ── Ancillary log repositories ────────────────────────────────────────────────

class RiskLogRepository:
    async def create(self, entry: RiskLogInsert) -> None:
        if settings.dry_run:
            return

        def _insert():
            return get_client().table("risk_logs").insert(entry.model_dump()).execute()

        await _write(_insert)


class SecurityLogRepository:
    async def create(self, entry: SecurityLogInsert) -> None:
        if settings.dry_run:
            return

        def _insert():
            return get_client().table("security_logs").insert(entry.model_dump()).execute()

        await _write(_insert)


class AuditLogRepository:
    async def create(self, entry: AuditLogInsert) -> None:
        if settings.dry_run:
            return

        def _insert():
            return get_client().table("audit_logs").insert(entry.model_dump()).execute()

        await _write(_insert)


class SystemEvolutionRepository:
    async def create(self, report: SystemEvolutionReportInsert) -> str:
        if settings.dry_run:
            return "dry-run-evolution-report-id"

        def _insert():
            return (
                get_client().table("system_evolution_reports")
                .insert(report.model_dump())
                .execute()
            )
        result = await _write(_insert)
        if not result.data:
            raise RuntimeError("system_evolution_reports insert returned no rows")
        return result.data[0]["id"]
