"""
In-process heartbeat tracker.

Each long-running worker calls `tracker.beat(name, status, **fields)` after
a successful iteration. The tracker:

  • holds the latest state per service in memory (single asyncio loop, no lock)
  • computes "stale" if last_seen is older than threshold
  • emits a periodic structured log entry summarising all services
  • is exposed through the /health endpoint

Status values used elsewhere:
  ok       — service ran an iteration successfully
  starting — initial state before the first beat
  paused   — explicitly halted (kill switch off, market data stale, etc.)
  error    — last iteration raised; supervisor is restarting
  stale    — derived: no beat within the staleness window
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from src.logging_config import get_logger
from src.utils.time import utcnow_iso

log = get_logger(__name__)


class HeartbeatTracker:
    """Holds per-service state. Single instance per process."""

    def __init__(self, stale_after_seconds: float = 60.0) -> None:
        self._stale_after = stale_after_seconds
        self._states:    dict[str, dict[str, Any]] = {}
        self._monotonic: dict[str, float] = {}

    def register(self, service: str) -> None:
        """Pre-register a service so it shows in /health before its first beat."""
        if service not in self._states:
            self._states[service]    = {"service": service, "status": "starting", "last_seen": None}
            self._monotonic[service] = time.monotonic()

    def beat(self, service: str, status: str = "ok", **fields: Any) -> None:
        self._states[service] = {
            "service":   service,
            "status":    status,
            "last_seen": utcnow_iso(),
            **fields,
        }
        self._monotonic[service] = time.monotonic()

    def state(self, service: str) -> dict[str, Any] | None:
        return self._states.get(service)

    def all(self) -> dict[str, dict[str, Any]]:
        """Return a snapshot. Computes derived `stale` if a service hasn't beaten
        within `stale_after_seconds`."""
        now = time.monotonic()
        snap: dict[str, dict[str, Any]] = {}
        for name, st in self._states.items():
            last = self._monotonic.get(name, 0.0)
            entry = dict(st)
            if st.get("status") == "starting":
                pass  # don't mark as stale before first beat
            elif (now - last) > self._stale_after:
                entry["status"]  = "stale"
                entry["stale_for_seconds"] = round(now - last, 1)
            snap[name] = entry
        return snap

    def is_stale(self, service: str) -> bool:
        last = self._monotonic.get(service)
        if last is None:
            return True
        return (time.monotonic() - last) > self._stale_after


# Singleton instance — imported and shared across modules
tracker = HeartbeatTracker()


async def heartbeat_log_loop(
    interval_seconds: float = 30.0,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Logs a structured summary of all heartbeats every `interval_seconds`."""
    log.info("heartbeat.loop_started", interval_s=interval_seconds)
    try:
        while True:
            if stop_event is not None and stop_event.is_set():
                return
            try:
                states = tracker.all()
                ok      = [s for s in states.values() if s.get("status") == "ok"]
                problem = [s for s in states.values() if s.get("status") not in ("ok", "starting")]
                log.info(
                    "heartbeat.tick",
                    services=list(states.keys()),
                    ok_count=len(ok),
                    problem_count=len(problem),
                    problems=[{"s": p["service"], "st": p["status"]} for p in problem],
                )
            except Exception as exc:
                log.error("heartbeat.tick_failed", error=str(exc)[:200])
            await asyncio.sleep(interval_seconds)
    except asyncio.CancelledError:
        log.info("heartbeat.loop_stopped")
        raise
