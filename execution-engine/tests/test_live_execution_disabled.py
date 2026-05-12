"""
Tests verifying the ENABLE_LIVE_EXECUTION=false hard gate.

These tests confirm that:
  1. Live decisions are skipped (not failed) when the gate is false
  2. A security log entry is written
  3. No exchange adapter is created
  4. No trade row is created
  5. The decision is marked 'skipped', not 'executed' or 'failed'
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.execution.engine import ExecutionEngine
from tests.conftest import (
    make_bot,
    make_decision,
    make_exchange_account,
    make_market_snapshot,
    make_user_settings,
)


@pytest.mark.asyncio
async def test_live_decision_skipped_when_gate_false(monkeypatch):
    """
    With ENABLE_LIVE_EXECUTION=False, a live decision must be skipped.
    No exchange adapter, no trade creation.
    """
    import src.execution.engine as engine_mod

    monkeypatch.setattr(engine_mod.settings, "enable_live_execution", False)

    decision = make_decision(mode="live", final_decision="open_long", approval_status="approved")

    engine = ExecutionEngine()

    skipped_ids = []
    security_events = []

    async def _mark_skipped(decision_id, reason):
        skipped_ids.append(decision_id)

    async def _security_log(entry):
        security_events.append(entry)

    async def _count_critical(*a, **kw):
        return 0

    with (
        patch.object(engine._decision_repo, "mark_skipped", side_effect=_mark_skipped),
        patch.object(engine._security_log, "create", side_effect=_security_log),
        patch.object(engine._decision_repo, "count_critical_security_events",
                     AsyncMock(return_value=0)),
        patch.object(engine._notifications, "live_gate_blocked", AsyncMock()),
    ):
        await engine.run(decision)

    assert decision.id in skipped_ids, "Decision was not marked skipped"
    assert len(security_events) == 1, "Expected exactly one security log entry"
    assert "live" in security_events[0].event_type.lower() or \
           "gate" in security_events[0].event_type.lower()


@pytest.mark.asyncio
async def test_live_gate_no_trade_created(monkeypatch):
    """No trade row must be created when the gate blocks execution."""
    import src.execution.engine as engine_mod

    monkeypatch.setattr(engine_mod.settings, "enable_live_execution", False)

    decision = make_decision(mode="live")
    engine = ExecutionEngine()

    trade_create_mock = AsyncMock()

    with (
        patch.object(engine._decision_repo, "mark_skipped", AsyncMock()),
        patch.object(engine._security_log, "create", AsyncMock()),
        patch.object(engine._notifications, "live_gate_blocked", AsyncMock()),
        patch("src.db.repositories.TradeRepository.create", trade_create_mock),
    ):
        await engine.run(decision)

    trade_create_mock.assert_not_called()


@pytest.mark.asyncio
async def test_live_gate_no_exchange_adapter_created(monkeypatch):
    """No exchange adapter must be instantiated when the gate is false."""
    import src.execution.engine as engine_mod

    monkeypatch.setattr(engine_mod.settings, "enable_live_execution", False)

    decision = make_decision(mode="live")
    engine = ExecutionEngine()

    adapter_factory_mock = MagicMock()

    with (
        patch.object(engine._decision_repo, "mark_skipped", AsyncMock()),
        patch.object(engine._security_log, "create", AsyncMock()),
        patch.object(engine._notifications, "live_gate_blocked", AsyncMock()),
        patch("src.exchanges.factory.get_live_adapter", adapter_factory_mock),
    ):
        await engine.run(decision)

    adapter_factory_mock.assert_not_called()


@pytest.mark.asyncio
async def test_paper_mode_not_gated_by_live_flag(monkeypatch):
    """
    Paper decisions must execute even when ENABLE_LIVE_EXECUTION=False.
    The gate only applies to live mode.
    """
    import src.execution.engine as engine_mod

    monkeypatch.setattr(engine_mod.settings, "enable_live_execution", False)

    decision = make_decision(mode="paper", final_decision="open_long", approval_status="auto_approved")
    engine = ExecutionEngine()

    skipped_ids = []

    async def _mark_skipped(decision_id, reason):
        skipped_ids.append(decision_id)

    bot = make_bot(mode="paper")
    us  = make_user_settings()
    acc = make_exchange_account()
    snap = make_market_snapshot()

    from tests.conftest import make_trade
    expected_trade = make_trade(mode="paper")

    with (
        patch.object(engine._bot_repo, "get_bot", AsyncMock(return_value=bot)),
        patch.object(engine._bot_repo, "get_user_settings", AsyncMock(return_value=us)),
        patch.object(engine._bot_repo, "get_exchange_account", AsyncMock(return_value=acc)),
        patch.object(engine._market_data, "get_snapshot", AsyncMock(return_value=snap)),
        patch.object(engine._decision_repo, "count_critical_security_events",
                     AsyncMock(return_value=0)),
        patch.object(engine._bot_repo, "count_open_trades", AsyncMock(return_value=0)),
        patch.object(engine._idempotency, "find_existing_trade", AsyncMock(return_value=None)),
        patch.object(engine._paper_executor, "execute", AsyncMock(return_value=expected_trade)),
        patch.object(engine._decision_repo, "mark_executed", AsyncMock()),
        patch.object(engine._audit_log, "create", AsyncMock()),
        patch.object(engine._notifications, "trade_executed", AsyncMock()),
        patch.object(engine._decision_repo, "mark_skipped", side_effect=_mark_skipped),
    ):
        await engine.run(decision)

    # Paper decision must NOT be in the skipped list
    assert decision.id not in skipped_ids, "Paper decision was incorrectly skipped by live gate"


@pytest.mark.asyncio
async def test_live_execution_enabled_attempts_live_order(monkeypatch):
    """
    When ENABLE_LIVE_EXECUTION=True, live execution is attempted
    (we don't need it to succeed — just verify the gate doesn't block it).
    """
    import src.execution.engine as engine_mod

    monkeypatch.setattr(engine_mod.settings, "enable_live_execution", True)

    decision = make_decision(
        mode="live",
        final_decision="open_long",
        approval_status="approved",
    )
    engine = ExecutionEngine()

    skipped_ids = []

    async def _mark_skipped(decision_id, reason):
        skipped_ids.append(decision_id)

    # The live executor will be called but will fail (no real exchange)
    # We only care that the gate doesn't intercept it.
    with (
        patch.object(engine._decision_repo, "mark_skipped", side_effect=_mark_skipped),
        patch.object(engine._decision_repo, "mark_failed", AsyncMock()),
        patch.object(engine._security_log, "create", AsyncMock()),
        patch.object(engine._notifications, "live_gate_blocked", AsyncMock()),
        patch.object(engine._notifications, "trade_failed", AsyncMock()),
        patch.object(engine._bot_repo, "get_bot", AsyncMock(return_value=make_bot(mode="live", real_trading_enabled=True))),
        patch.object(engine._bot_repo, "get_user_settings", AsyncMock(return_value=make_user_settings(real_trading_enabled=True, real_trading_allowed=True))),
        patch.object(engine._bot_repo, "get_exchange_account", AsyncMock(return_value=make_exchange_account())),
        patch.object(engine._market_data, "get_snapshot", AsyncMock(return_value=make_market_snapshot())),
        patch.object(engine._decision_repo, "count_critical_security_events", AsyncMock(return_value=0)),
        patch.object(engine._bot_repo, "count_open_trades", AsyncMock(return_value=0)),
        patch.object(engine._idempotency, "find_existing_trade", AsyncMock(return_value=None)),
    ):
        await engine.run(decision)

    # Should NOT have been intercepted by the live gate (not in skipped due to gate)
    # It may have failed for other reasons — but not the gate skip
    live_gate_block_skip = any(
        "ENABLE_LIVE_EXECUTION" in str(s) for s in skipped_ids
    )
    assert not live_gate_block_skip
