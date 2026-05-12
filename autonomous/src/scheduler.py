"""
Tiny interval scheduler.

`run_interval(coro_factory, interval)` calls `coro_factory()` every
`interval` seconds until cancelled. Errors in the callable are caught and
logged; the next iteration still runs on schedule.

The Scheduler is independent of the Worker base class — Workers handle their
own loops, while the Scheduler is for one-off coroutines you want to run
periodically without subclassing.
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from src.logging_config import get_logger

log = get_logger(__name__)


async def run_interval(
    name:    str,
    factory: Callable[[], Awaitable[None]],
    *,
    interval_seconds: float,
    initial_delay:    float = 0.0,
) -> None:
    if initial_delay > 0:
        await asyncio.sleep(initial_delay)
    log.info("scheduler.start", name=name, interval_s=interval_seconds)
    try:
        while True:
            try:
                await factory()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.exception("scheduler.iteration_error", name=name, error=str(exc)[:300])
            await asyncio.sleep(interval_seconds)
    except asyncio.CancelledError:
        log.info("scheduler.stopped", name=name)
        raise
