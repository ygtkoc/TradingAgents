"""
Autonomous service entrypoint.

Boots, in order:
  1. Heartbeat tracker (eager, registers slots).
  2. Health server   (so /health is available immediately).
  3. Market-data feed (WebSocket + REST fallback).
  4. Signal generator (every 60 s).
  5. Demo-bot bootstrap (every 30 s until first run succeeds).
  6. Heartbeat-log loop (every 30 s — structured summary to stdout).

A single `Supervisor` owns all in-process tasks. SIGINT/SIGTERM trigger a
clean shutdown that cancels every task and awaits its completion.

The autonomous service is paper-only and uses public Binance endpoints —
no API keys required. It NEVER writes to trades/trade_decisions/agent_runs.
"""
from __future__ import annotations

import asyncio
import signal
import sys
import time

from src.bootstrap import DemoBootstrap
from src.config import settings
from src.db.supabase_client import log_startup_auth, run_startup_self_test
from src.health import start_health_server
from src.heartbeat import heartbeat_log_loop, tracker
from src.logging_config import get_logger
from src.services.email import EmailDispatcher
from src.services.market_data import MarketDataCache, MarketDataFeed
from src.services.signal_generator import SignalGenerator
from src.supervisor import Supervisor

log = get_logger(__name__)


async def _amain() -> int:
    started_at = time.monotonic()
    log_startup_auth()
    run_startup_self_test()
    log.info(
        "autonomous.starting",
        worker_id=settings.autonomous_worker_id,
        symbols=settings.symbols,
        kline_interval=settings.market_data_kline_interval,
        seeder_interval_s=settings.signal_seeder_interval_seconds,
        bootstrap_enabled=settings.demo_bootstrap_enabled,
        dry_run=settings.dry_run,
    )

    # ── Initialise shared state ─────────────────────────────────────────────
    cache       = MarketDataCache()
    feed        = MarketDataFeed(cache=cache)
    seeder      = SignalGenerator(cache=cache)
    booter      = DemoBootstrap()
    emailer     = EmailDispatcher()

    supervisor = Supervisor()

    # ── Health server ──────────────────────────────────────────────────────
    health_runner = await start_health_server(started_at=started_at)

    # ── Pre-register all heartbeat slots so /health is informative pre-tick ─
    for s in ("market_data", "signal_generator", "bootstrap", "email_dispatcher", "heartbeat"):
        tracker.register(s)

    log.info(
        "autonomous.boot.success",
        worker_id=settings.autonomous_worker_id,
        elapsed_ms=round((time.monotonic() - started_at) * 1000),
    )

    # ── Spawn supervised tasks ─────────────────────────────────────────────
    supervisor.spawn("market_data",       feed.run)
    supervisor.spawn("signal_generator",  seeder.run)
    supervisor.spawn("bootstrap",         booter.run)
    supervisor.spawn("email_dispatcher",  emailer.run)
    supervisor.spawn(
        "heartbeat",
        lambda: heartbeat_log_loop(interval_seconds=30.0),
    )

    # ── Graceful shutdown wiring ───────────────────────────────────────────
    stop = asyncio.Event()

    def _request_stop() -> None:
        log.warning("autonomous.shutdown_signal_received")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            # Windows: signal handlers via add_signal_handler aren't supported;
            # KeyboardInterrupt below catches Ctrl+C instead.
            pass

    try:
        await stop.wait()
    except asyncio.CancelledError:
        pass

    log.info("autonomous.shutting_down")
    await supervisor.shutdown(timeout=10.0)
    await health_runner.cleanup()
    log.info("autonomous.stopped")
    return 0


def main() -> None:
    try:
        rc = asyncio.run(_amain())
    except KeyboardInterrupt:
        rc = 0
    sys.exit(rc)


if __name__ == "__main__":
    main()
