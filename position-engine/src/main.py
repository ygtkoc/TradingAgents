"""
Position Engine — entry point.

Continuously monitors open trades and applies lifecycle actions:
  - Stop-loss, take-profit, trailing stop triggers
  - Emergency close (global kill switch, unsafe exchange accounts)
  - Unrealized P&L updates
  - Exchange reconciliation

Safety invariants:
  1. ENABLE_LIVE_CLOSE defaults to False — live close is opt-in
  2. Never creates new trades — only updates existing ones
  3. Unknown exchange state → needs_reconciliation, never blind retry
  4. Atomic two-phase claim prevents duplicate processing
  5. All exceptions are caught — one bad trade never kills the worker

Usage:
    python -m src.main
    # or via process manager / Docker
"""
from __future__ import annotations

import asyncio
import signal
import sys

from src.config import settings
from src.db.supabase_client import log_startup_auth, run_startup_self_test
from src.lifecycle.engine import LifecycleEngine
from src.logging_config import get_logger

log = get_logger(__name__)


# ── Semaphore-guarded task wrapper ─────────────────────────────────────────────

async def _process_trade(
    engine: LifecycleEngine,
    trade,
    sem: asyncio.Semaphore,
    active_tasks: set,
) -> None:
    """Run one lifecycle cycle, bounded by the concurrency semaphore."""
    async with sem:
        try:
            await engine.run(trade)
        except Exception as exc:
            # engine.run() should never raise, but be defensive
            log.error(
                "main.unhandled_trade_exception",
                trade_id=trade.id,
                error=str(exc)[:300],
                exc_info=True,
            )


# ── Main loop ──────────────────────────────────────────────────────────────────

async def main() -> None:
    log_startup_auth()
    run_startup_self_test()
    log.info(
        "position_engine.starting",
        worker_id=settings.worker_id,
        dry_run=settings.dry_run,
        enable_live_close=settings.enable_live_close,
        poll_interval=settings.position_poll_interval_seconds,
        max_concurrent=settings.position_max_concurrent_runs,
    )

    if settings.dry_run:
        log.warning("position_engine.dry_run_mode", message="DB writes and exchange calls are disabled")

    if not settings.enable_live_close:
        log.warning(
            "position_engine.live_close_disabled",
            message=(
                "ENABLE_LIVE_CLOSE=false — live close orders will NOT be submitted. "
                "Set ENABLE_LIVE_CLOSE=true to enable after safety audit."
            ),
        )

    engine       = LifecycleEngine()
    sem          = asyncio.Semaphore(settings.position_max_concurrent_runs)
    active_tasks: set[asyncio.Task] = set()
    shutdown_event = asyncio.Event()

    # ── Graceful shutdown on SIGINT / SIGTERM ──────────────────────────────────
    loop = asyncio.get_running_loop()

    def _handle_signal(sig_name: str) -> None:
        log.info("position_engine.shutdown_signal", signal=sig_name)
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig.name: _handle_signal(s))
        except (NotImplementedError, RuntimeError):
            # Windows does not support add_signal_handler for all signals
            pass

    # ── Select queue implementation ────────────────────────────────────────────
    if settings.use_pgmq:
        from src.queue.pgmq import PgmqTradePoller as Poller
    else:
        from src.queue.polling import PollingTradePoller as Poller  # type: ignore[assignment]

    # ── Main processing loop ───────────────────────────────────────────────────
    async with Poller() as poller:
        async for trade in poller.poll():
            if shutdown_event.is_set():
                log.info("position_engine.draining", pending=len(active_tasks))
                poller.stop()
                break

            task = asyncio.create_task(
                _process_trade(engine, trade, sem, active_tasks),
                name=f"lifecycle-{trade.id[:8]}",
            )
            active_tasks.add(task)
            task.add_done_callback(active_tasks.discard)

    # ── Drain in-flight tasks ──────────────────────────────────────────────────
    if active_tasks:
        log.info("position_engine.draining_tasks", count=len(active_tasks))
        results = await asyncio.gather(*active_tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                log.error("position_engine.drain_error", error=str(r)[:200])

    log.info("position_engine.stopped", worker_id=settings.worker_id)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
