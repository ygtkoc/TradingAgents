"""
Agent Engine entry point.

Starts the signal processing loop:
  1. Polls the signals table for pending work (two-phase atomic claim).
  2. Sanitizes signal metadata before passing to the pipeline.
  3. For each claimed signal, loads bot context, runs the pipeline, persists results.
  4. Handles graceful shutdown on SIGTERM/SIGINT.
  5. Limits concurrent in-flight pipelines to settings.max_concurrent_runs.

Safety guarantees (enforced here):
  - Engine does NOT write to the trades table.
  - Engine does NOT call exchange APIs.
  - Output is exclusively trade_decisions rows.
  - service_role key is never logged or returned to callers.
  - signal.metadata is sanitized before entering the pipeline.
  - Veto decisions respect severity mapping (pause_trading / reject / wait).
  - Transient pipeline failures leave the signal in 'processing' for
    release_stuck_signals() to reset — no retry storm risk.
  - Permanent failures (injection, invalid signal) mark signal as 'failed'.

Usage:
    python -m src.main
"""
from __future__ import annotations

import asyncio
import signal
import sys
import time
from typing import Optional

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
    RiskLogRepository,
    SecurityLogRepository,
    SystemEvolutionRepository,
    TradeDecisionRepository,
)
from src.logging_config import get_logger
from src.orchestration.aggregator import aggregate
from src.orchestration.graph import TradingPipeline
from src.orchestration.state import PipelineState
from src.orchestration.veto import (
    build_veto_summary,
    collect_all_flags,
    derive_severity_from_flags,
    veto_summary_to_dict,
)
from src.queue.polling import PollingConsumer
from src.services.metadata import sanitize_metadata
from src.services.notifications import (
    notify_pipeline_error,
    notify_trade_decision,
    notify_veto,
)
from src.utils.time import utcnow_iso

log = get_logger(__name__)

# ── Repositories (module-level singletons) ────────────────────────────────────
_bot_repo = BotRepository()
_run_repo = AgentRunRepository()
_output_repo = AgentOutputRepository()
_decision_repo = TradeDecisionRepository()
_audit_repo = AuditLogRepository()
_risk_log_repo = RiskLogRepository()
_security_log_repo = SecurityLogRepository()
_evolution_repo = SystemEvolutionRepository()


# ── Graceful shutdown ─────────────────────────────────────────────────────────

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
    """Install graceful shutdown handlers in a cross-platform way.

    asyncio.loop.add_signal_handler() is not implemented on Windows
    ProactorEventLoop. On Windows, fall back to signal.signal() so Ctrl+C
    still requests a clean shutdown instead of crashing at startup.
    """
    loop = asyncio.get_running_loop()

    def _request_shutdown(*_args: object) -> None:
        _shutdown.request()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _shutdown.request)
        except (NotImplementedError, RuntimeError, ValueError):
            # Windows fallback: SIGTERM may not be supported in every runtime,
            # but SIGINT/Ctrl+C should be handled cleanly.
            try:
                signal.signal(sig, _request_shutdown)
            except (ValueError, OSError, RuntimeError):
                log.debug(
                    "signal_handler.unsupported",
                    signal=getattr(sig, "name", str(sig)),
                )


# ── Context loader ────────────────────────────────────────────────────────────

async def _load_signal_context(
    sig: Signal,
) -> tuple[Optional[Bot], Optional[BotConfig], Optional[UserSettings], int]:
    """
    Loads bot, config, user_settings, and open_trade_count for a signal.
    Returns (None, None, None, 0) if the bot is not found.
    """
    if not sig.bot_id:
        log.warning("signal.no_bot_id", signal_id=str(sig.id))
        return None, None, None, 0

    bot = await _bot_repo.get_bot(str(sig.bot_id))
    if bot is None:
        log.warning("signal.bot_not_found", signal_id=str(sig.id), bot_id=str(sig.bot_id))
        return None, None, None, 0

    config = await _bot_repo.get_active_config(bot)
    user_settings = await _bot_repo.get_user_settings(str(bot.user_id))
    open_trades = await _bot_repo.count_open_trades(str(bot.id))

    return bot, config, user_settings, open_trades


# ── Persistence ───────────────────────────────────────────────────────────────

async def _persist_results(
    sig: Signal,
    bot: Optional[Bot],
    user_settings: Optional[UserSettings],
    state: PipelineState,
    pipeline_duration_ms: int,
) -> None:
    """
    Writes all pipeline outputs to the database.

    Write order (critical first, best-effort last):
      1. Update AgentRun status
      2. Bulk insert agent_outputs
      3. Create trade_decision  ← primary output
      4. Link trade_decision → agent_run
      5. Write risk_logs        (fire-and-forget)
      6. Write security_logs    (fire-and-forget)
      7. Write system_evolution_reports (fire-and-forget)
      8. Write audit_logs       (fire-and-forget)
      9. User notifications     (fire-and-forget)

    This function NEVER writes to the trades table.
    Trade execution is the responsibility of the Execution Engine.
    """
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

    # ── 1. Update AgentRun status ─────────────────────────────────────────────
    try:
        await _run_repo.update_status(
            run_id=agent_run_id,
            status=AgentRunStatus.COMPLETED.value,
            completed_at=utcnow_iso(),
            duration_ms=pipeline_duration_ms,
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
    except Exception as exc:
        log.error("persist.run_update_failed", error=str(exc), run_id=agent_run_id)

    # ── 2. Bulk insert agent outputs ──────────────────────────────────────────
    try:
        output_inserts = [
            AgentOutputInsert(
                agent_run_id=agent_run_id,
                agent_definition_id=r.get("agent_definition_id", ""),
                user_id=sig.user_id,
                bot_id=sig.bot_id,
                decision=r.get("decision", "wait"),
                score=r.get("score", 0.0),
                confidence=r.get("confidence", 0.0),
                veto=r.get("veto", False),
                reasoning=r.get("reasoning", "")[:2000],
                output=r.get("output", {}),
                error_message=r.get("error"),
                duration_ms=r.get("duration_ms"),
                completed_at=utcnow_iso(),
            )
            for r in agent_results
        ]
        await _output_repo.bulk_create(output_inserts)
    except Exception as exc:
        log.error("persist.outputs_failed", error=str(exc), count=len(agent_results))

    # ── 3. Create TradeDecision ───────────────────────────────────────────────
    # This is the primary output of the engine. Never touches trades table.
    trade_decision_id: Optional[str] = None
    try:
        decision_insert = TradeDecisionInsert(
            user_id=sig.user_id,
            bot_id=sig.bot_id,
            agent_run_id=agent_run_id,
            signal_id=str(sig.id),
            exchange=sig.exchange,
            symbol=sig.symbol,
            direction=sig.direction.value,
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
            },
            security_summary={
                "flags": security_flags,
                "injection_detected": any(
                    f in security_flags for f in (
                        "metadata_injection_attempt", "agent_reasoning_injection",
                        "signal_field_injection",
                    )
                ),
                "metadata_suspicious": state.get("metadata_suspicious", False),
            },
            veto_summary=veto_summary_dict or {},
            agent_outputs_snapshot={
                "count": len(agent_results),
                "agents": [r.get("agent_name") for r in agent_results],
            },
            metadata={"dry_run": settings.dry_run},
        )
        trade_decision_id = await _decision_repo.create(decision_insert)
    except Exception as exc:
        log.error("persist.decision_failed", error=str(exc), signal_id=str(sig.id))

    # ── 4. Link decision back to agent run ────────────────────────────────────
    if trade_decision_id:
        try:
            await _run_repo.update_status(
                run_id=agent_run_id,
                status=AgentRunStatus.COMPLETED.value,
                trade_decision_id=trade_decision_id,
            )
        except Exception as exc:
            log.error("persist.run_link_failed", error=str(exc))

    # ── 5. Risk logs ──────────────────────────────────────────────────────────
    if risk_flags and not settings.dry_run:
        try:
            severity = derive_severity_from_flags(risk_flags, [])
            await _risk_log_repo.create(
                RiskLogInsert(
                    user_id=sig.user_id,
                    bot_id=sig.bot_id,
                    trade_decision_id=trade_decision_id,
                    agent_run_id=agent_run_id,
                    risk_type="pipeline_risk_flags",
                    severity=severity.value,
                    triggered=veto_triggered and veto_agent and _is_risk_veto(veto_agent),
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
        except Exception as exc:
            log.error("persist.risk_log_failed", error=str(exc))

    # ── 6. Security logs ──────────────────────────────────────────────────────
    if security_flags or state.get("metadata_suspicious"):
        if not settings.dry_run:
            try:
                severity = derive_severity_from_flags([], security_flags)
                if state.get("metadata_suspicious"):
                    # Metadata injection is at least HIGH
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
            except Exception as exc:
                log.error("persist.security_log_failed", error=str(exc))

    # ── 7. System evolution report (fire-and-forget) ──────────────────────────
    if evolution_report and not settings.dry_run:
        try:
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
        except Exception as exc:
            log.error("persist.evolution_failed", error=str(exc))

    # ── 8. Audit log (fire-and-forget) ────────────────────────────────────────
    try:
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
    except Exception as exc:
        log.error("persist.audit_failed", error=str(exc))

    # ── 9. User notifications (fire-and-forget) ───────────────────────────────
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


def _is_risk_veto(veto_agent_name: str) -> bool:
    """Returns True if the vetoing agent is a risk-category agent."""
    return "risk" in veto_agent_name.lower()


# ── Single signal processor ───────────────────────────────────────────────────

async def _process_signal(
    sig: Signal,
    pipeline: TradingPipeline,
    consumer: PollingConsumer,
    semaphore: asyncio.Semaphore,
) -> None:
    """
    Processes a single claimed signal end-to-end.

    The signal is already in 'processing' status when this function is called.
    On transient failure: leave in 'processing' (release_stuck_signals resets it).
    On permanent failure: call consumer.nack_permanent() → status='failed'.
    On success: call consumer.ack() → status='processed'.
    """
    async with semaphore:
        signal_id = str(sig.id)
        start_ms = int(time.monotonic() * 1000)

        # ── FIX 6: Sanitize metadata BEFORE loading context or running pipeline ─
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
            # Permanent failure — injection in signal metadata
            await consumer.nack_permanent(
                sig,
                "Injection patterns detected in signal metadata. Signal rejected.",
            )
            return

        # ── Load context ──────────────────────────────────────────────────────
        bot, config, user_settings, open_trades = await _load_signal_context(sig)

        # ── Create AgentRun row ───────────────────────────────────────────────
        try:
            run_insert = AgentRunInsert(
                user_id=sig.user_id,
                bot_id=sig.bot_id,
                run_status=AgentRunStatus.RUNNING.value,
                trigger_type="signal",
                started_at=utcnow_iso(),
                input_snapshot={"signal_id": signal_id, "symbol": sig.symbol},
            )
            agent_run_id = await _run_repo.create(run_insert)
        except Exception as exc:
            log.error("process.run_create_failed", signal_id=signal_id, error=str(exc))
            # Transient DB error — leave signal in 'processing' for stuck-signals handler
            return

        # ── Run pipeline ──────────────────────────────────────────────────────
        state: Optional[PipelineState] = None
        duration_ms = 0
        try:
            state = await asyncio.wait_for(
                pipeline.run(
                    signal=sig.model_dump(),
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

            # ── FIX 3: Compute approval status from aggregator ────────────────
            # The graph's aggregate_node already called aggregate() with bot/user context.
            # The approval_status and manual_approval_required are already in state.

            log.info(
                "pipeline.completed",
                signal_id=signal_id,
                final_decision=state.get("final_decision"),
                approval_status=state.get("approval_status"),
                manual_approval_required=state.get("manual_approval_required"),
                score=state.get("aggregated_score"),
                duration_ms=duration_ms,
                veto=state.get("veto_triggered"),
            )

        except asyncio.TimeoutError:
            duration_ms = int(time.monotonic() * 1000) - start_ms
            log.error(
                "pipeline.timeout",
                signal_id=signal_id,
                timeout_s=settings.pipeline_timeout_seconds,
            )
            await _run_repo.update_status(
                run_id=agent_run_id,
                status=AgentRunStatus.TIMEOUT.value,
                completed_at=utcnow_iso(),
                duration_ms=duration_ms,
                error_message=f"Timeout after {settings.pipeline_timeout_seconds}s",
            )
            # Leave signal in 'processing' — release_stuck_signals() resets after 5 min
            asyncio.create_task(
                notify_pipeline_error(signal_id, "Pipeline timeout", settings.worker_id)
            )
            return

        except Exception as exc:
            duration_ms = int(time.monotonic() * 1000) - start_ms
            log.exception("pipeline.error", signal_id=signal_id, error=str(exc)[:300])
            await _run_repo.update_status(
                run_id=agent_run_id,
                status=AgentRunStatus.FAILED.value,
                completed_at=utcnow_iso(),
                duration_ms=duration_ms,
                error_message=str(exc)[:500],
            )
            # Leave signal in 'processing' — release_stuck_signals() handles retry
            asyncio.create_task(
                notify_pipeline_error(signal_id, str(exc)[:200], settings.worker_id)
            )
            return

        # ── Persist results ───────────────────────────────────────────────────
        try:
            await _persist_results(
                sig=sig,
                bot=bot,
                user_settings=user_settings,
                state=state,
                pipeline_duration_ms=duration_ms,
            )
        except Exception as exc:
            log.error("persist.unhandled_error", signal_id=signal_id, error=str(exc))
            # Pipeline ran successfully; best-effort persistence.
            # Still ack the signal so it isn't reprocessed.

        # ── Ack signal: status → 'processed' ─────────────────────────────────
        await consumer.ack(sig)


# ── Main loop ─────────────────────────────────────────────────────────────────

async def run() -> None:
    """
    Main async entry point.
    Builds the pipeline, starts the consumer loop, handles graceful shutdown.
    """
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
                # Shutdown requested — return signal to queue (it's still 'processing',
                # release_stuck_signals will reset it within 5 min)
                log.info("shutdown.skipping_signal", signal_id=str(sig.id))
                break

            task = asyncio.create_task(
                _process_signal(sig, pipeline, consumer, semaphore)
            )
            in_flight.add(task)
            task.add_done_callback(in_flight.discard)

        if in_flight:
            log.info("shutdown.draining", in_flight=len(in_flight))
            await asyncio.gather(*in_flight, return_exceptions=True)

    log.info("agent_engine.stopped")


def main() -> None:
    """Synchronous entry point for CLI / service runner."""
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
