"""
Agent Engine entry point.
"""
from __future__ import annotations

import asyncio
import signal
import sys
import time
from typing import Any, Optional

from src.config import settings
from src.db.models import (
    AgentOutputInsert,
    AgentRunInsert,
    AgentRunStatus,
    AuditLogInsert,
    Bot,
    BotConfig,
    RiskLogInsert,
    SecurityLogInsert,
    SeverityLevel,
    Signal,
    SystemEvolutionReportInsert,
    TradeDecisionInsert,
    UserSettings,
)
from src.db.repositories import (
    AgentOutputRepository,
    AgentRunRepository,
    AuditLogRepository,
    BotRepository,
    PaperExecutionRepository,
    RiskLogRepository,
    SecurityLogRepository,
    SignalRepository,
    SystemEvolutionRepository,
    TradeDecisionRepository,
)
from src.db.supabase_client import get_client, log_startup_auth, run_startup_self_test
from src.logging_config import get_logger
from src.orchestration.graph import TradingPipeline
from src.orchestration.state import PipelineState
from src.orchestration.veto import collect_all_flags, derive_severity_from_flags
from src.queue.polling import PollingConsumer
from src.services.metadata import sanitize_metadata
from src.services.reward_plan import build_reward_plan, final_take_profit
from src.services.notifications import (
    notify_pipeline_error,
    notify_trade_decision,
    notify_veto,
)
from src.utils.time import utcnow_iso

log = get_logger(__name__)

_bot_repo          = BotRepository()
_paper_exec_repo   = PaperExecutionRepository()
_run_repo = AgentRunRepository()
_output_repo = AgentOutputRepository()
_decision_repo = TradeDecisionRepository()
_audit_repo = AuditLogRepository()
_risk_log_repo = RiskLogRepository()
_security_log_repo = SecurityLogRepository()
_signal_repo = SignalRepository()
_evolution_repo = SystemEvolutionRepository()


def _num(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _external_signal_risk(sig: Signal) -> dict[str, Any]:
    """Extract safe numeric trade parameters from external signal metadata."""
    meta = sig.metadata or {}
    if meta.get("source") != "telegram":
        return {}

    entry = _num(meta.get("entry_price"))
    stop_loss = _num(meta.get("stop_loss"))
    take_profits = meta.get("take_profits")
    take_profit = None
    if isinstance(take_profits, list) and take_profits:
        take_profit = _num(take_profits[0])

    risk: dict[str, Any] = {
        "external_source": "telegram",
        "sizing_model": "external_signal_with_engine_risk",
        "order_type": "market",
        "margin_mode": "cross",
        "leverage_policy": "exchange_max_allowed",
    }
    if entry and entry > 0:
        risk["entry_price"] = entry
    if stop_loss and stop_loss > 0:
        risk["stop_loss"] = stop_loss
    if take_profit and take_profit > 0:
        risk["take_profit"] = take_profit
    if entry and stop_loss and take_profit and abs(entry - stop_loss) > 0:
        risk["risk_reward_ratio"] = abs(take_profit - entry) / abs(entry - stop_loss)
    return risk


class ShutdownFlag:
    def __init__(self) -> None:
        self._event = asyncio.Event()

    def request(self) -> None:
        log.warning("shutdown.requested")
        self._event.set()

    @property
    def is_set(self) -> bool:
        return self._event.is_set()


_shutdown = ShutdownFlag()


def _install_signal_handlers() -> None:
    loop = asyncio.get_running_loop()

    def _request_shutdown(*_args: object) -> None:
        _shutdown.request()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _shutdown.request)
        except (NotImplementedError, RuntimeError, ValueError):
            try:
                signal.signal(sig, _request_shutdown)
            except (ValueError, OSError, RuntimeError):
                log.debug(
                    "signal_handler.unsupported",
                    signal=getattr(sig, "name", str(sig)),
                )


async def _load_signal_context(
    sig: Signal,
) -> tuple[Optional[Bot], Optional[BotConfig], Optional[UserSettings], int]:
    if not sig.bot_id:
        log.warning("signal.no_bot_id", signal_id=str(sig.id))
        return None, None, None, 0

    bot = await _bot_repo.get_bot(str(sig.bot_id))
    if bot is None:
        log.warning("signal.bot_not_found", signal_id=str(sig.id), bot_id=str(sig.bot_id))
        return None, None, None, 0

    config = await _bot_repo.get_active_config(bot)
    user_settings = await _bot_repo.get_user_settings(str(bot.user_id))
    open_trades = await _bot_repo.count_open_trades(
        bot_id=str(bot.id),
        user_id=str(bot.user_id),
        mode=bot.mode.value,          # only count same-mode trades
    )
    return bot, config, user_settings, open_trades


async def _persist_results(
    sig: Signal,
    bot: Optional[Bot],
    state: PipelineState,
    pipeline_duration_ms: int,
) -> str:
    agent_run_id = state.get("agent_run_id", "unknown")
    agent_results = state.get("agent_results", [])
    final_decision = state.get("final_decision", "wait")
    aggregated_score = state.get("aggregated_score", 0.0)
    decision_reasoning = state.get("decision_reasoning", "")
    decision_confidence = state.get("decision_confidence", 0.0)
    approval_status = state.get("approval_status", "auto_approved")
    manual_approval_required = state.get("manual_approval_required", False)
    veto_triggered = state.get("veto_triggered", False)
    veto_agent = state.get("veto_agent_name")
    veto_summary_dict = state.get("veto_summary")
    evolution_report = state.get("evolution_report")

    risk_flags, security_flags = collect_all_flags(agent_results)
    external_risk = _external_signal_risk(sig)
    reward_plan = state.get("reward_plan") or {}
    reward_take_profit = final_take_profit(reward_plan) if isinstance(reward_plan, dict) else None

    output_inserts = [
        AgentOutputInsert(
            agent_run_id=agent_run_id,
            agent_definition_id=result.get("agent_definition_id", ""),
            user_id=sig.user_id,
            bot_id=sig.bot_id,
            decision=result.get("decision", "wait"),
            score=result.get("score", 0.0),
            confidence=result.get("confidence", 0.0),
            veto=result.get("veto", False),
            reasoning=result.get("reasoning", "")[:2000],
            output={
                **(result.get("output") or {}),
                "agent_name": result.get("agent_name"),
                "agent_category": result.get("agent_category"),
            },
            error_message=result.get("error"),
            duration_ms=result.get("duration_ms"),
            completed_at=utcnow_iso(),
        )
        for result in agent_results
    ]
    await _output_repo.bulk_create(output_inserts)

    log.info(
        "trade_decision.create.start",
        agent_run_id=agent_run_id,
        signal_id=str(sig.id),
        symbol=sig.symbol,
        final_decision=final_decision,
        approval_status=approval_status,
    )
    decision_insert = TradeDecisionInsert(
        user_id=sig.user_id,
        bot_id=sig.bot_id,
        agent_run_id=agent_run_id,
        signal_id=str(sig.id),
        exchange=sig.exchange,
        symbol=sig.symbol,
        direction=state.get("effective_direction") or sig.direction.value,
        mode=bot.mode.value if bot else "paper",
        final_decision=final_decision,
        approval_status=approval_status,
        manual_approval_required=manual_approval_required,
        score_summary={
            "aggregated_score": aggregated_score,
            "confidence": decision_confidence,
            "reasoning": decision_reasoning[:1000],
        },
        risk_summary={
            "flags": risk_flags,
            "veto_triggered": veto_triggered,
            "veto_agent": veto_agent,
            "risk_score": state.get("risk_score", 100.0),
            "data_quality_score": state.get("data_quality_score", 100.0),
            "manipulation_score_penalty": state.get("manipulation_score_penalty", 0.0),
            "reward_plan": reward_plan,
            "tp_plan": reward_plan.get("levels", []) if isinstance(reward_plan, dict) else [],
            "risk_reward_ratio": state.get("selected_reward_r"),
            "max_reward_r": state.get("max_reward_r"),
            "min_reward_r": state.get("min_reward_r"),
            "take_profit": reward_take_profit,
            **external_risk,
        },
        security_summary={
            "flags": security_flags,
            "injection_detected": any(
                flag in security_flags
                for flag in (
                    "metadata_injection_attempt",
                    "agent_reasoning_injection",
                    "signal_field_injection",
                )
            ),
            "metadata_suspicious": state.get("metadata_suspicious", False),
        },
        veto_summary=veto_summary_dict or {},
        agent_outputs_snapshot={
            "count": len(agent_results),
            "agents": [result.get("agent_name") for result in agent_results],
        },
        suggested_entry_price=external_risk.get("entry_price"),
        suggested_stop_loss=external_risk.get("stop_loss"),
        suggested_take_profit=external_risk.get("take_profit") or reward_take_profit,
        metadata={
            "dry_run": settings.dry_run,
            "warming_up": state.get("warming_up", False),
            "external_signal_source": external_risk.get("external_source"),
            "telegram_source_id": (sig.metadata or {}).get("telegram_source_id"),
            "telegram_message_id": (sig.metadata or {}).get("telegram_message_id"),
            "rejection_reason": (
                "insufficient_history_warming_up"
                if state.get("warming_up")
                else None
            ),
        },
        execution_status="pending_execution",
    )
    trade_decision_id = await _decision_repo.create(decision_insert)
    if not trade_decision_id:
        raise RuntimeError("trade decision create returned no id")

    await _run_repo.update_status(
        run_id=agent_run_id,
        status=AgentRunStatus.COMPLETED.value,
        completed_at=utcnow_iso(),
        duration_ms=pipeline_duration_ms,
        trade_decision_id=trade_decision_id,
        final_summary={
            "final_decision": final_decision,
            "aggregated_score": aggregated_score,
            "approval_status": approval_status,
            "veto_triggered": veto_triggered,
            "veto_agent": veto_agent,
            "risk_flags": risk_flags,
            "security_flags": security_flags,
        },
    )

    if risk_flags and not settings.dry_run:
        severity = derive_severity_from_flags(risk_flags, [])
        await _risk_log_repo.create(
            RiskLogInsert(
                user_id=sig.user_id,
                bot_id=sig.bot_id,
                trade_decision_id=trade_decision_id,
                agent_run_id=agent_run_id,
                risk_type="pipeline_risk_flags",
                severity=severity.value,
                triggered=bool(veto_triggered and veto_agent and _is_risk_veto(veto_agent)),
                message=(
                    f"Risk flags detected during pipeline run for {sig.symbol}: "
                    f"{', '.join(risk_flags[:10])}"
                ),
                metadata={
                    "flags": risk_flags,
                    "final_decision": final_decision,
                    "aggregated_score": aggregated_score,
                    "risk_score": state.get("risk_score"),
                },
            )
        )

    if security_flags or state.get("metadata_suspicious"):
        if not settings.dry_run:
            severity = derive_severity_from_flags([], security_flags)
            if state.get("metadata_suspicious"):
                severity = SeverityLevel.HIGH
            await _security_log_repo.create(
                SecurityLogInsert(
                    user_id=sig.user_id,
                    event_type="pipeline_security_flags",
                    severity=severity.value,
                    source="agent_engine",
                    message=(
                        f"Security flags for signal {sig.id} "
                        f"({sig.symbol} on {sig.exchange}): "
                        f"{', '.join(security_flags or ['metadata_suspicious'])}"
                    ),
                    metadata={
                        "security_flags": security_flags,
                        "metadata_suspicious": state.get("metadata_suspicious", False),
                        "metadata_oversize": state.get("metadata_oversize", False),
                        "final_decision": final_decision,
                        "veto_triggered": veto_triggered,
                        "signal_id": str(sig.id),
                    },
                )
            )

    if evolution_report and not settings.dry_run:
        await _evolution_repo.create(
            SystemEvolutionReportInsert(
                generated_by_agent="system_evolution_agent",
                agent_run_id=agent_run_id,
                finding_type="pipeline_run_summary",
                description=(
                    f"Pipeline run for {sig.symbol} on {sig.exchange}. "
                    f"Decision: {final_decision}. Score: {aggregated_score:.1f}."
                ),
                status="open",
                metadata=evolution_report,
            )
        )

    await _audit_repo.create(
        AuditLogInsert(
            user_id=sig.user_id,
            action="pipeline_completed",
            record_id=str(sig.id),
            table_name="signals",
            source="agent_engine",
            metadata={
                "final_decision": final_decision,
                "approval_status": approval_status,
                "manual_approval_required": manual_approval_required,
                "trade_decision_id": trade_decision_id,
                "agent_run_id": agent_run_id,
                "duration_ms": pipeline_duration_ms,
                "worker_id": settings.worker_id,
                "dry_run": settings.dry_run,
                "veto_triggered": veto_triggered,
            },
        )
    )

    if bot:
        if veto_triggered and veto_agent:
            asyncio.create_task(
                notify_veto(
                    user_id=str(bot.user_id),
                    bot_id=str(bot.id),
                    symbol=sig.symbol,
                    veto_agent=veto_agent,
                    reason=decision_reasoning[:300],
                    flags=risk_flags + security_flags,
                )
            )
        else:
            asyncio.create_task(
                notify_trade_decision(
                    user_id=str(bot.user_id),
                    bot_id=str(bot.id),
                    symbol=sig.symbol,
                    decision=final_decision,
                    score=aggregated_score,
                    reasoning=decision_reasoning[:300],
                    decision_id=trade_decision_id,
                    dry_run=settings.dry_run,
                )
            )

    return trade_decision_id


def _is_risk_veto(veto_agent_name: str) -> bool:
    return "risk" in veto_agent_name.lower()


def _bot_metadata(bot_dict: dict[str, Any], bot: "Bot") -> dict[str, Any]:
    meta = bot_dict.get("metadata")
    if isinstance(meta, dict):
        return meta
    return getattr(bot, "metadata", {}) or {}


def _trading_system(bot_dict: dict[str, Any], bot: "Bot") -> str:
    meta = _bot_metadata(bot_dict, bot)
    return str(
        meta.get("trading_system")
        or meta.get("system")
        or bot_dict.get("trading_system")
        or "futures_trading"
    )


def _risk_profile(bot_dict: dict[str, Any], bot: "Bot") -> dict[str, float]:
    if _trading_system(bot_dict, bot) == "portfolio_management":
        return {
            "max_risk_pct": 10.0,
            "min_stop_pct": 3.0,
            "max_stop_pct": 18.0,
            "min_rr": 1.2,
            "max_position_pct": 100.0,
        }
    return {
        "max_risk_pct": 10.0,
        "min_stop_pct": 1.5,
        "max_stop_pct": 12.0,
        "min_rr": 2.0,
        # Futures paper sizing is risk-based: a 2% account risk with a ~2%
        # stop naturally needs close to 100% notional exposure. A small
        # position-size cap silently shrinks the trade and makes the stored
        # risk_amount lie, so keep this cap at least 100% for this profile.
        "max_position_pct": 100.0,
    }


async def _execute_paper_trade(
    *,
    sig: Signal,
    bot: "Bot",
    state: PipelineState,
    trade_decision_id: str,
) -> None:
    """Inline paper execution engine.

    Triggered after a pipeline run produces open_long/open_short with
    approval_status=auto_approved in paper mode. Implements the 2% risk rule:

        risk_amount  = balance × risk_per_trade_pct / 100
        stop_dist    = ATR × 2   (or 2% of price if ATR unavailable)
        position_qty = risk_amount / (entry_price × stop_dist_pct / 100)
        take_profit  = entry ± risk_reward_ratio × stop_dist
        notional     = entry_price × position_qty

    Errors are logged and the decision is marked 'failed' so the UI can
    surface the reason. The worker continues regardless.
    """
    decision_id = trade_decision_id
    worker_id   = settings.worker_id

    try:
        # ── 1. Claim the decision ─────────────────────────────────────────────
        claimed = await _paper_exec_repo.claim_decision(decision_id, worker_id)
        if not claimed:
            log.info(
                "paper_exec.already_claimed",
                decision_id=decision_id,
            )
            return

        # ── 2. Fetch paper balance ────────────────────────────────────────────
        acct = await _paper_exec_repo.get_paper_balance(str(sig.user_id))
        if not acct or acct.get("status") != "active":
            reason = f"Paper account not active (status={acct.get('status') if acct else 'missing'})"
            await _paper_exec_repo.mark_decision_failed(decision_id, reason, worker_id)
            log.warning("paper_exec.account_not_active", decision_id=decision_id, reason=reason)
            return

        balance = float(acct["balance"])
        if balance <= 0:
            reason = "Paper balance is zero or depleted"
            await _paper_exec_repo.mark_decision_failed(decision_id, reason, worker_id)
            # Mark account as depleted so signal generator stops seeding
            try:
                from src.db.supabase_client import get_client as _gc
                _gc().table("paper_accounts").update({"status": "depleted"}).eq(
                    "user_id", str(sig.user_id)
                ).execute()
            except Exception:
                pass
            log.warning("paper_exec.balance_depleted", user_id=str(sig.user_id))
            return

        # ── 3. Compute position sizing (2% risk rule) ─────────────────────────
        snapshot_dict = state.get("market_snapshot") or {}
        external_risk = _external_signal_risk(sig)
        entry_price   = float(snapshot_dict.get("close_price") or 0)
        if external_risk.get("entry_price"):
            entry_price = float(external_risk["entry_price"])
        if entry_price <= 0:
            reason = f"Invalid entry price {entry_price} from market snapshot"
            await _paper_exec_repo.mark_decision_failed(decision_id, reason, worker_id)
            return

        final_decision  = state.get("final_decision", "")
        direction       = "long" if "long" in final_decision else "short"
        side            = "buy"  if direction == "long" else "sell"

        # ── Flexible risk model (migration 0012) ─────────────────────────────
        # Supports: percentage (% of balance) and fixed_usd (dollar amount).
        bot_dict_exec    = state.get("bot") or {}
        trading_system   = _trading_system(bot_dict_exec, bot)
        risk_profile     = _risk_profile(bot_dict_exec, bot)
        user_settings_exec = state.get("user_settings") or {}
        risk_model       = "percentage"
        risk_value_raw   = (
            user_settings_exec.get("default_risk_per_trade_pct")
            or bot_dict_exec.get("risk_value")
            or bot.risk_per_trade_pct
            or 2.0
        )
        risk_value       = float(risk_value_raw)
        user_max_reward_r = float(user_settings_exec.get("max_reward_r") or 5.0)
        user_min_reward_r = float(user_settings_exec.get("min_reward_r") or risk_profile["min_rr"])

        if trading_system == "portfolio_management" and direction == "short":
            reason = "Portfolio management profile does not open short/futures-style positions"
            await _paper_exec_repo.mark_decision_failed(decision_id, reason, worker_id)
            return

        if risk_model == "fixed_usd":
            # Fixed dollar amount — cap at available balance
            max_profile_risk = balance * risk_profile["max_risk_pct"] / 100.0
            risk_amount = min(risk_value, max_profile_risk, balance)
            risk_pct    = (risk_amount / balance * 100.0) if balance > 0 else 0.0
        else:
            # Percentage of balance — clamp to 0.1%–10%
            risk_pct    = min(max(risk_value, 0.1), risk_profile["max_risk_pct"])
            risk_amount = balance * risk_pct / 100.0

        # Stop distance: prefer ATR-based, fall back to 2% of price
        atr_pct         = state.get("atr_pct")
        stop_dist_pct   = (atr_pct * 2.0) if atr_pct and atr_pct > 0 else 2.0
        stop_dist_pct   = min(
            max(stop_dist_pct, risk_profile["min_stop_pct"]),
            risk_profile["max_stop_pct"],
        )

        stop_dist_abs   = entry_price * stop_dist_pct / 100.0
        if direction == "long":
            stop_loss   = entry_price - stop_dist_abs
        else:
            stop_loss   = entry_price + stop_dist_abs

        if external_risk.get("stop_loss"):
            stop_loss = float(external_risk["stop_loss"])
            stop_dist_abs = abs(entry_price - stop_loss)
        if stop_dist_abs <= 0:
            reason = "External signal stop-loss produces zero risk distance"
            await _paper_exec_repo.mark_decision_failed(decision_id, reason, worker_id)
            return

        # Position size: risk_amount / stop_distance_per_unit
        intended_risk_amount = risk_amount
        position_qty  = risk_amount / stop_dist_abs if stop_dist_abs > 0 else 0.0
        # Cap to max position size %
        max_pos_pct   = risk_profile["max_position_pct"]
        max_qty       = (balance * max_pos_pct / 100.0) / entry_price
        uncapped_qty  = position_qty
        position_qty  = min(position_qty, max_qty)

        if position_qty <= 0:
            reason = "Computed position size is zero or negative"
            await _paper_exec_repo.mark_decision_failed(decision_id, reason, worker_id)
            return

        capped_by_position_size = position_qty < uncapped_qty
        actual_risk_amount = stop_dist_abs * position_qty
        if capped_by_position_size:
            risk_amount = actual_risk_amount
            risk_pct = (risk_amount / balance * 100.0) if balance > 0 else 0.0

        notional        = entry_price * position_qty
        reward_plan = state.get("reward_plan") or {}
        if not reward_plan:
            requested_r = (
                float(external_risk["risk_reward_ratio"])
                if external_risk.get("risk_reward_ratio")
                else None
            )
            reward_plan = build_reward_plan(
                entry_price=entry_price,
                stop_loss=stop_loss,
                direction=direction,
                requested_reward_r=requested_r,
                max_reward_r=user_max_reward_r,
                min_reward_r=user_min_reward_r,
                close_profile="balanced",
                source="agent_engine_inline_fallback",
                rationale="Inline paper executor generated fallback reward plan.",
                confidence=0.65,
            )
        risk_reward_ratio = float((reward_plan or {}).get("selected_reward_r") or user_min_reward_r)
        take_profit = (
            float(external_risk["take_profit"])
            if external_risk.get("take_profit")
            else float(final_take_profit(reward_plan) or 0.0)
        )
        if take_profit <= 0:
            reason = "Reward planner did not produce a valid take-profit"
            await _paper_exec_repo.mark_decision_failed(decision_id, reason, worker_id)
            return
        expected_reward = risk_amount * risk_reward_ratio

        # ── 4. Insert trade row ───────────────────────────────────────────────
        now_iso = utcnow_iso()
        trade_row = {
            "user_id":            str(sig.user_id),
            "bot_id":             str(sig.bot_id),
            "trade_decision_id":  decision_id,
            "exchange":           sig.exchange,
            "symbol":             sig.symbol,
            "side":               side,
            "direction":          direction,
            "mode":               "paper",
            "status":             "open",
            "entry_price":        entry_price,
            "quantity":           position_qty,
            "filled_quantity":    position_qty,
            "avg_entry_price":    entry_price,
            "stop_loss":          stop_loss,
            "take_profit":        take_profit,
            "risk_amount":        risk_amount,
            "risk_percent":       risk_pct,
            "risk_reward_ratio":  risk_reward_ratio,
            "expected_reward":    expected_reward,
            "notional":           notional,
            "metadata": {
                "atr_pct":          atr_pct,
                "stop_dist_pct":    stop_dist_pct,
                "aggregated_score": state.get("aggregated_score"),
                "decision_reasoning": (state.get("decision_reasoning") or "")[:500],
                "worker_id":        worker_id,
                "trading_system":   trading_system,
                "risk_profile":     risk_profile,
                "intended_risk_amount": intended_risk_amount,
                "actual_risk_amount":   actual_risk_amount,
                "position_size_capped": capped_by_position_size,
                "uncapped_quantity":    uncapped_qty,
                "max_quantity":         max_qty,
                "reserved_on_open":  False,
                "paper_fill_status": "filled",
                "reward_plan":       reward_plan,
                "tp_plan":           reward_plan.get("levels", []),
            },
        }

        trade_id = await _paper_exec_repo.insert_trade(trade_row)
        log.info(
            "paper_trade.created",
            trade_id=trade_id,
            decision_id=decision_id,
            symbol=sig.symbol,
            direction=direction,
            entry_price=entry_price,
            quantity=round(position_qty, 8),
            notional=round(notional, 2),
            stop_loss=round(stop_loss, 8),
            take_profit=round(take_profit, 8),
            risk_amount=round(risk_amount, 2),
            risk_pct=risk_pct,
        )

        # ── 5. Debit paper balance (reserve risk capital) ─────────────────────
        new_balance = balance

        # ── 6. Insert paper_account_events debit ─────────────────────────────
        await _paper_exec_repo.insert_paper_event({
            "account_id":       acct["id"],
            "user_id":          str(sig.user_id),
            "trade_id":         trade_id,
            "event_type":       "paper_trade_opened",
            "delta":            0.0,
            "realized_delta":   0.0,
            "unrealized_delta": 0.0,
            "balance_after":    balance,
            "realized_after":   float(acct.get("realized_pnl") or 0),
            "unrealized_after": 0.0,
            "note": (
                f"Paper trade opened: {direction} {sig.symbol} "
                f"× {position_qty:.6f} @ {entry_price:.4f} "
                f"| Risk {risk_pct:.1f}% = ${risk_amount:.2f} | "
                f"SL {stop_loss:.4f} TP {take_profit:.4f}"
            ),
            "metadata": {
                "trade_id": trade_id,
                "decision_id": decision_id,
                "risk_amount": risk_amount,
                "reserved_on_open": False,
            },
        })

        # ── 7. Mark decision executed ─────────────────────────────────────────
        await _paper_exec_repo.mark_decision_executed(decision_id, trade_id, worker_id)

        # ── 8. Audit trade_event ──────────────────────────────────────────────
        await _paper_exec_repo.insert_trade_event({
            "trade_id":         trade_id,
            "trade_decision_id": decision_id,
            "bot_id":           str(sig.bot_id),
            "user_id":          str(sig.user_id),
            "event_type":       "paper_trade_opened",
            "details": {
                "entry_price":   entry_price,
                "quantity":      position_qty,
                "notional":      notional,
                "stop_loss":     stop_loss,
                "take_profit":   take_profit,
                "risk_amount":   risk_amount,
                "risk_percent":  risk_pct,
                "expected_reward": expected_reward,
                "reward_plan": reward_plan,
                "tp_plan": reward_plan.get("levels", []),
                "direction":     direction,
                "balance_before": balance,
                "balance_after":  balance,
                "reserved_on_open": False,
            },
        })

        try:
            get_client().table("notifications").insert({
                "user_id": str(sig.user_id),
                "type": "trade_opened",
                "title": "İşlem açıldı",
                "message": (
                    f"{direction.upper()} {sig.symbol} işlemi {entry_price:.8g} giriş fiyatıyla açıldı. "
                    f"Miktar {position_qty:.8g}, notional ${notional:.2f}, "
                    f"SL {stop_loss:.8g}, TP {take_profit:.8g}, "
                    f"1R ${risk_amount:.2f}."
                ),
                "is_read": False,
                "related_table": "trades",
                "related_id": trade_id,
                "priority": 2,
                "metadata": {
                    "trade_id": trade_id,
                    "decision_id": decision_id,
                    "symbol": sig.symbol,
                    "direction": direction,
                    "side": side,
                    "mode": "paper",
                    "entry_price": entry_price,
                    "quantity": position_qty,
                    "notional": notional,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                    "risk_amount": risk_amount,
                    "risk_percent": risk_pct,
                },
            }).execute()
        except Exception as exc:
            log.warning("notification.trade_opened_insert_failed", error=str(exc)[:200])

    except Exception as exc:
        error_text = str(exc).encode("ascii", "backslashreplace").decode("ascii")[:500]
        log.error(
            "paper_exec.failed",
            decision_id=decision_id,
            error=error_text,
        )
        try:
            await _paper_exec_repo.mark_decision_failed(decision_id, error_text, worker_id)
        except Exception:
            pass   # best effort


async def _fail_signal_pipeline(
    *,
    sig: Signal,
    agent_run_id: Optional[str],
    duration_ms: int,
    error_message: str,
    notify_message: str,
    log_event: str,
) -> None:
    safe_error = error_message.encode("ascii", "backslashreplace").decode("ascii")[:500]
    log.error(
        log_event,
        signal_id=str(sig.id),
        agent_run_id=agent_run_id,
        error=safe_error,
        duration_ms=duration_ms,
    )
    if agent_run_id:
        await _run_repo.update_status(
            run_id=agent_run_id,
            status=AgentRunStatus.FAILED.value,
            completed_at=utcnow_iso(),
            duration_ms=duration_ms,
            error_message=safe_error,
        )
    await _signal_repo.mark_failed(str(sig.id), safe_error)
    asyncio.create_task(
        notify_pipeline_error(str(sig.id), notify_message[:200], settings.worker_id)
    )


async def _process_signal(
    sig: Signal,
    pipeline: TradingPipeline,
    consumer: PollingConsumer,
    semaphore: asyncio.Semaphore,
) -> None:
    async with semaphore:
        signal_id = str(sig.id)
        start_ms = int(time.monotonic() * 1000)
        agent_run_id: Optional[str] = None

        try:
            raw_metadata = sig.metadata or {}
            sanitized_meta, meta_suspicious, meta_oversize = sanitize_metadata(
                raw_metadata, signal_id=signal_id
            )

            if meta_suspicious:
                log.warning(
                    "signal.metadata_injection_detected",
                    signal_id=signal_id,
                    symbol=sig.symbol,
                )
                await consumer.nack_permanent(
                    sig,
                    "Injection patterns detected in signal metadata. Signal rejected.",
                )
                return

            bot, config, user_settings, open_trades = await _load_signal_context(sig)
            agent_run_id = await _run_repo.create(
                AgentRunInsert(
                    user_id=sig.user_id,
                    bot_id=sig.bot_id,
                    run_status=AgentRunStatus.RUNNING.value,
                    trigger_type="signal",
                    started_at=utcnow_iso(),
                    input_snapshot={"signal_id": signal_id, "symbol": sig.symbol},
                )
            )

            state = await asyncio.wait_for(
                pipeline.run(
                    signal=sig,
                    bot=bot.model_dump() if bot else None,
                    bot_config=config.model_dump() if config else None,
                    user_settings=user_settings.model_dump() if user_settings else None,
                    open_trade_count=open_trades,
                    agent_run_id=agent_run_id,
                    sanitized_metadata=sanitized_meta,
                    metadata_suspicious=meta_suspicious,
                    metadata_oversize=meta_oversize,
                ),
                timeout=settings.pipeline_timeout_seconds,
            )
            duration_ms = int(time.monotonic() * 1000) - start_ms
            trade_decision_id = await _persist_results(
                sig=sig,
                bot=bot,
                state=state,
                pipeline_duration_ms=duration_ms,
            )

            log.info(
                "pipeline.completed",
                signal_id=signal_id,
                agent_run_id=agent_run_id,
                trade_decision_id=trade_decision_id,
                final_decision=state.get("final_decision"),
                approval_status=state.get("approval_status"),
                manual_approval_required=state.get("manual_approval_required"),
                score=state.get("aggregated_score"),
                duration_ms=duration_ms,
                veto=state.get("veto_triggered"),
            )

            # ── Inline paper execution ────────────────────────────────────────
            # For paper bots with auto-approved open_long/open_short decisions,
            # execute immediately in-process rather than requiring a separate
            # execution engine service.
            final_decision  = state.get("final_decision", "")
            approval_status = state.get("approval_status", "")
            if (
                settings.enable_inline_paper_execution
                and
                bot is not None
                and bot.mode.value == "paper"
                and final_decision in ("open_long", "open_short")
                and approval_status in ("auto_approved", "approved")
                and not settings.dry_run
                and not state.get("warming_up", False)
            ):
                asyncio.create_task(
                    _execute_paper_trade(
                        sig=sig,
                        bot=bot,
                        state=state,
                        trade_decision_id=trade_decision_id,
                    )
                )

            await consumer.ack(sig)
        except Exception as exc:
            duration_ms = int(time.monotonic() * 1000) - start_ms
            log_event = "pipeline.timeout" if isinstance(exc, asyncio.TimeoutError) else "pipeline.failed"
            notify_message = "Pipeline timeout" if isinstance(exc, asyncio.TimeoutError) else str(exc)
            error_message = "pipeline timeout" if isinstance(exc, asyncio.TimeoutError) else str(exc)
            await _fail_signal_pipeline(
                sig=sig,
                agent_run_id=agent_run_id,
                duration_ms=duration_ms,
                error_message=error_message,
                notify_message=notify_message,
                log_event=log_event,
            )


async def run() -> None:
    log_startup_auth()
    run_startup_self_test()
    log.info(
        "agent_engine.starting",
        worker_id=settings.worker_id,
        dry_run=settings.dry_run,
        max_concurrent=settings.max_concurrent_runs,
        poll_interval=settings.poll_interval_seconds,
    )

    if settings.dry_run:
        log.warning("agent_engine.dry_run_mode", message="No real writes will be made")

    _install_signal_handlers()
    pipeline = await TradingPipeline.build()
    semaphore = asyncio.Semaphore(settings.max_concurrent_runs)
    in_flight: set[asyncio.Task] = set()
    consumer = PollingConsumer()

    async with consumer:
        async for sig in consumer.consume():
            if _shutdown.is_set:
                log.info("shutdown.skipping_signal", signal_id=str(sig.id))
                break

            task = asyncio.create_task(_process_signal(sig, pipeline, consumer, semaphore))
            in_flight.add(task)
            task.add_done_callback(in_flight.discard)

        if in_flight:
            log.info("shutdown.draining", in_flight=len(in_flight))
            await asyncio.gather(*in_flight, return_exceptions=True)

    log.info("agent_engine.stopped")


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
