"""
Execution Engine entry point.

Starts the polling consumer and runs the execution pipeline in a loop.
Handles graceful shutdown on SIGINT / SIGTERM.

Run with:
    python -m src.main
    # or
    python src/main.py

Environment:
    Copy .env.example → .env and fill in your values.
    ENABLE_LIVE_EXECUTION must be explicitly set to true to place real orders.
"""
from __future__ import annotations

import asyncio
import signal
import sys

from src.config import settings
from src.db.supabase_client import log_startup_auth, run_startup_self_test
from src.execution.engine import ExecutionEngine
from src.logging_config import get_logger
from src.queue.polling import PollingConsumer

log = get_logger(__name__)

_SEMAPHORE: asyncio.Semaphore | None = None


def _log_startup_banner() -> None:
    log.info(
        "execution_engine.starting",
        worker_id=settings.worker_id,
        enable_live_execution=settings.enable_live_execution,
        poll_interval_s=settings.poll_interval_seconds,
        max_concurrent_runs=settings.max_concurrent_runs,
        dry_run=settings.dry_run,
        log_level=settings.log_level,
    )
    if settings.enable_live_execution:
        log.warning(
            "execution_engine.live_execution_enabled",
            warning="ENABLE_LIVE_EXECUTION=true — real orders will be placed on the exchange",
        )
    else:
        log.info(
            "execution_engine.live_execution_disabled",
            note="Set ENABLE_LIVE_EXECUTION=true to enable real exchange orders",
        )

    if settings.dry_run:
        log.warning(
            "execution_engine.dry_run_active",
            note="DRY_RUN=true — all DB writes and exchange calls are skipped",
        )


async def _process_decision(engine: ExecutionEngine, decision, sem: asyncio.Semaphore) -> None:
    """Run a single decision through the engine, bounded by the concurrency semaphore."""
    async with sem:
        await engine.run(decision)


async def main() -> None:
    log_startup_auth()
    run_startup_self_test()
    _log_startup_banner()

    engine = ExecutionEngine()
    sem    = asyncio.Semaphore(settings.max_concurrent_runs)

    shutdown_event = asyncio.Event()

    def _handle_signal(sig) -> None:
        log.info("execution_engine.shutdown_signal", signal=sig.name)
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig: _handle_signal(s))
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            signal.signal(sig, lambda s, f: _handle_signal(signal.Signals(s)))

    active_tasks: set[asyncio.Task] = set()

    async with PollingConsumer() as consumer:
        log.info("execution_engine.running", worker_id=settings.worker_id)

        async for decision in consumer.consume():
            if shutdown_event.is_set():
                consumer.stop()
                break

            task = asyncio.create_task(
                _process_decision(engine, decision, sem),
                name=f"exec-{decision.id[:8]}",
            )
            active_tasks.add(task)
            task.add_done_callback(active_tasks.discard)

        # Graceful drain: wait for in-flight tasks
        if active_tasks:
            log.info(
                "execution_engine.draining",
                pending=len(active_tasks),
            )
            await asyncio.gather(*active_tasks, return_exceptions=True)

    log.info("execution_engine.stopped", worker_id=settings.worker_id)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
