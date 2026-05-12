"""
Base async-worker pattern.

A `Worker` runs an iteration on an interval until cancelled. Each successful
iteration emits a heartbeat. Errors are logged and the worker keeps going —
the Supervisor handles restart on terminal failure.
"""
from __future__ import annotations

import abc
import asyncio
from typing import Any

from src.heartbeat import tracker
from src.logging_config import get_logger

log = get_logger(__name__)


class Worker(abc.ABC):
    """Override `tick()` (one iteration) and `interval_seconds`."""

    name:               str   = "worker"
    interval_seconds:   float = 60.0
    paused_status_name: str   = "paused"

    def __init__(self) -> None:
        tracker.register(self.name)

    @abc.abstractmethod
    async def tick(self) -> None:
        """Run a single iteration. Should return quickly; long-running operations
        belong in a different `Worker` subclass with its own loop semantics."""

    async def run(self) -> None:
        """Main loop. Heartbeats on each iteration. Sleeps `interval_seconds`."""
        log.info("worker.start", name=self.name, interval_s=self.interval_seconds)
        try:
            while True:
                try:
                    await self.tick()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log.exception("worker.tick_error", name=self.name, error=str(exc)[:300])
                    tracker.beat(self.name, "error", error=str(exc)[:200])
                await asyncio.sleep(self.interval_seconds)
        except asyncio.CancelledError:
            log.info("worker.stopped", name=self.name)
            raise

    def beat_ok(self, **fields: Any) -> None:
        tracker.beat(self.name, "ok", **fields)

    def beat_paused(self, **fields: Any) -> None:
        tracker.beat(self.name, self.paused_status_name, **fields)
