from __future__ import annotations

import pytest

from src.db import repositories
from src.db.repositories import TradeLifecycleRepository


class _CountQuery:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.count = 0

    def select(self, *args, **kwargs):
        self.calls.append(("select", args + tuple(kwargs.items())))
        return self

    def eq(self, *args):
        self.calls.append(("eq", args))
        return self

    def neq(self, *args):
        self.calls.append(("neq", args))
        return self

    def gte(self, *args):
        self.calls.append(("gte", args))
        return self

    def execute(self):
        return self


class _Client:
    def __init__(self, query: _CountQuery) -> None:
        self.query = query

    def table(self, name: str):
        assert name == "security_logs"
        return self.query


@pytest.mark.asyncio
async def test_critical_security_count_only_uses_unresolved_real_incidents():
    query = _CountQuery()
    repo = TradeLifecycleRepository()
    repo._client = _Client(query)  # type: ignore[assignment]

    count = await repo.count_critical_security_events("user-001")

    assert count == 0
    assert ("eq", ("severity", "critical")) in query.calls
    assert ("eq", ("resolved", False)) in query.calls
    assert ("neq", ("event_type", "security_guard_blocked_execution")) in query.calls
    assert ("neq", ("event_type", "live_close_blocked")) in query.calls


@pytest.mark.asyncio
async def test_run_retries_transient_supabase_http2_errors(monkeypatch):
    calls = 0
    sleeps: list[float] = []

    async def fake_to_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    async def fake_sleep(seconds: float):
        sleeps.append(seconds)

    def flaky_call():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeError("<StreamReset stream_id:175, error_code:5, remote_reset:True>")
        return "ok"

    monkeypatch.setattr(repositories.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(repositories.asyncio, "sleep", fake_sleep)

    assert await repositories._run(flaky_call) == "ok"
    assert calls == 3
    assert sleeps == [0.2, 0.4]

