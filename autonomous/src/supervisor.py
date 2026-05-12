"""
In-process supervisor.

`Supervisor.spawn(name, factory)` registers a coroutine *factory* (a no-arg
callable returning a coroutine) and runs it under a wrapper that:

  1. Catches non-cancellation exceptions, logs, and restarts the coroutine
     with exponential backoff (1s → 2s → 4s … up to 60s).
  2. Stops cleanly on `shutdown()` — cancels the inner task, awaits it.
  3. After `max_restart_attempts` consecutive crashes, marks the service
     `"failed"` in the heartbeat tracker and stops trying (poison-pill guard).

The Supervisor manages *in-process* asyncio tasks. Cross-process supervision
of the agent / execution / position engines is handled by
`scripts/dev_autonomous.py`, which runs them as subprocesses.
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from src.heartbeat import tracker
from src.logging_config import get_logger

log = get_logger(__name__)

CoroFactory = Callable[[], Awaitable[None]]


class Supervisor:
    def __init__(
        self,
        max_restart_attempts: int = 10,
        backoff_initial:      float = 1.0,
        backoff_max:          float = 60.0,
    ) -> None:
        self._tasks:                dict[str, asyncio.Task[None]] = {}
        self._stop                  = asyncio.Event()
        self._max_restart_attempts  = max_restart_attempts
        self._backoff_initial       = backoff_initial
        self._backoff_max           = backoff_max

    def spawn(self, name: str, factory: CoroFactory) -> asyncio.Task[None]:
        if name in self._tasks:
            raise ValueError(f"task already registered: {name}")

        async def wrapper() -> None:
            attempts = 0
            backoff  = self._backoff_initial
            while not self._stop.is_set():
                try:
                    log.info("supervisor.task_start", name=name, attempt=attempts + 1)
                    await factory()
                    # Coro completed normally — exit loop, do not restart.
                    log.info("supervisor.task_finished", name=name)
                    return
                except asyncio.CancelledError:
                    log.info("supervisor.task_cancelled", name=name)
                    raise
                except Exception as exc:
                    attempts += 1
                    tracker.beat(name, "error", error=str(exc)[:200], attempts=attempts)
                    log.exception(
                        "supervisor.task_crashed",
                        name=name,
                        error=str(exc)[:300],
                        attempts=attempts,
                    )
                    if attempts >= self._max_restart_attempts:
                        tracker.beat(name, "failed", error="max_restart_attempts", attempts=attempts)
                        log.error("supervisor.task_giving_up", name=name, attempts=attempts)
                        return
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2.0, self._backoff_max)

        task = asyncio.create_task(wrapper(), name=name)
        self._tasks[name] = task
        return task

    @property
    def tasks(self) -> dict[str, asyncio.Task[None]]:
        return dict(self._tasks)

    async def shutdown(self, timeout: float = 10.0) -> None:
        log.info("supervisor.shutdown_requested", task_count=len(self._tasks))
        self._stop.set()
        for t in self._tasks.values():
            t.cancel()
        if self._tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._tasks.values(), return_exceptions=True),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                log.warning("supervisor.shutdown_timeout")
        log.info("supervisor.shutdown_complete")
