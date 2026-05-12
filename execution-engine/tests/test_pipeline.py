"""
End-to-end pipeline tests for ExecutionEngine.

These tests mock all I/O (DB, exchange) and verify the pipeline
orchestration logic: context loading, guard invocation, executor routing,
idempotency recovery, and failure handling.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db.models import PlatformSettings
from src.execution.engine import ExecutionEngine
from src.guards.risk_guard import RiskGuardResult
from src.guards.security_guard import SecurityGuardResult
from tests.conftest import (
    make_bot,
    make_decision,
    make_exchange_account,
    make_market_snapshot,
    make_trade,
    make_user_settings,
)


def _safe_security_result() -> SecurityGuardResult:
    return SecurityGuardResult(blocked=False, reason="all security checks passed")


def _safe_risk_result() -> RiskGuardResult:
    return RiskGuardResult(blocked=False, reason="all checks passed")


def _blocked_security_result(reason: str = "test block") -> SecurityGuardResult:
    return SecurityGuardResult(blocked=True, reason=reason)


def _blocked_risk_result(reason: str = "test block") -> RiskGuardResult:
    return RiskGuardResult(blocked=True, reason=reason)


def _make_engine_with_mocks(decision, *, mode="paper"):
    """Build an engine with all I/O mocked for the given decision."""
    bot = make_bot(mode=mode)
    us  = make_user_settings()
    acc = make_exchange_account()
    snap = make_market_snapshot(close_price=50_000.0)

    engine = ExecutionEngine()
    mocks = {
        "get_bot":       AsyncMock(return_value=bot),
        "get_user_settings": AsyncMock(return_value=us),
        "get_exchange_account": AsyncMock(return_value=acc),
        "get_snapshot":  AsyncMock(return_value=snap),
        "count_critical_security_events": AsyncMock(return_value=0),
        "count_open_trades": AsyncMock(return_value=0),
        "find_existing_trade": AsyncMock(return_value=None),
        "mark_executed": AsyncMock(),
        "mark_failed":   AsyncMock(),
        "mark_skipped":  AsyncMock(),
        "create_audit":  AsyncMock(),
        "create_risk":   AsyncMock(),
        "create_security": AsyncMock(),
        "notify_executed": AsyncMock(),
        "notify_skipped":  AsyncMock(),
        "notify_failed":   AsyncMock(),
        "platform_settings_get": AsyncMock(return_value=PlatformSettings()),
    }
    return engine, mocks, bot, us, acc, snap


@pytest.mark.asyncio
async def test_paper_pipeline_success():
    """Happy path: paper decision executes and marks decision as executed."""
    decision = make_decision(mode="paper")
    engine, mocks, bot, us, acc, snap = _make_engine_with_mocks(decision)
    expected_trade = make_trade(mode="paper")

    with (
        patch.object(engine._bot_repo, "get_bot", mocks["get_bot"]),
        patch.object(engine._bot_repo, "get_user_settings", mocks["get_user_settings"]),
        patch.object(engine._bot_repo, "get_exchange_account", mocks["get_exchange_account"]),
        patch.object(engine._market_data, "get_snapshot", mocks["get_snapshot"]),
        patch.object(engine._decision_repo, "count_critical_security_events",
                     mocks["count_critical_security_events"]),
        patch.object(engine._bot_repo, "count_open_trades", mocks["count_open_trades"]),
        patch.object(engine._idempotency, "find_existing_trade", mocks["find_existing_trade"]),
        patch.object(engine._paper_executor, "execute", AsyncMock(return_value=expected_trade)),
        patch.object(engine._decision_repo, "mark_executed", mocks["mark_executed"]),
        patch.object(engine._decision_repo, "mark_failed", mocks["mark_failed"]),
        patch.object(engine._decision_repo, "mark_skipped", mocks["mark_skipped"]),
        patch.object(engine._audit_log, "create", mocks["create_audit"]),
        patch.object(engine._notifications, "trade_executed", mocks["notify_executed"]),
    ):
        await engine.run(decision)

    mocks["mark_executed"].assert_called_once_with(decision.id, expected_trade.id)
    mocks["mark_failed"].assert_not_called()
    mocks["mark_skipped"].assert_not_called()


@pytest.mark.asyncio
async def test_security_guard_block_skips_decision():
    """Security guard failure → mark_skipped, no trade created."""
    decision = make_decision(
        security_summary={"injection_detected": True}
    )
    engine, mocks, bot, us, acc, snap = _make_engine_with_mocks(decision)
    mock_execute = AsyncMock()

    with (
        patch.object(engine._platform_repo, "get", mocks["platform_settings_get"]),
        patch.object(engine._bot_repo, "get_bot", mocks["get_bot"]),
        patch.object(engine._bot_repo, "get_user_settings", mocks["get_user_settings"]),
        patch.object(engine._bot_repo, "get_exchange_account", mocks["get_exchange_account"]),
        patch.object(engine._market_data, "get_snapshot", mocks["get_snapshot"]),
        patch.object(engine._decision_repo, "count_critical_security_events",
                     mocks["count_critical_security_events"]),
        patch.object(engine._decision_repo, "mark_skipped", mocks["mark_skipped"]),
        patch.object(engine._decision_repo, "mark_failed", mocks["mark_failed"]),
        patch.object(engine._decision_repo, "mark_executed", mocks["mark_executed"]),
        patch.object(engine._security_log, "create", AsyncMock()),
        patch.object(engine._notifications, "trade_skipped", mocks["notify_skipped"]),
        patch.object(engine._paper_executor, "execute", mock_execute),
    ):
        await engine.run(decision)

    mocks["mark_skipped"].assert_called_once()
    mocks["mark_executed"].assert_not_called()
    # Paper executor should NOT have been called
    mock_execute.assert_not_called()


@pytest.mark.asyncio
async def test_vetoed_decision_blocked_by_security_guard():
    """decision with veto_summary.vetoed=True must be blocked."""
    decision = make_decision(
        veto_summary={"vetoed": True, "resolved_decision": "pause_trading", "veto_reason": "injection"},
    )
    engine, mocks, bot, us, acc, snap = _make_engine_with_mocks(decision)

    with (
        patch.object(engine._bot_repo, "get_bot", mocks["get_bot"]),
        patch.object(engine._bot_repo, "get_user_settings", mocks["get_user_settings"]),
        patch.object(engine._bot_repo, "get_exchange_account", mocks["get_exchange_account"]),
        patch.object(engine._market_data, "get_snapshot", mocks["get_snapshot"]),
        patch.object(engine._decision_repo, "count_critical_security_events",
                     mocks["count_critical_security_events"]),
        patch.object(engine._decision_repo, "mark_skipped", mocks["mark_skipped"]),
        patch.object(engine._decision_repo, "mark_failed", mocks["mark_failed"]),
        patch.object(engine._decision_repo, "mark_executed", mocks["mark_executed"]),
        patch.object(engine._security_log, "create", AsyncMock()),
        patch.object(engine._notifications, "trade_skipped", AsyncMock()),
        patch.object(engine._paper_executor, "execute", AsyncMock()),
    ):
        await engine.run(decision)

    mocks["mark_skipped"].assert_called_once()
    mocks["mark_executed"].assert_not_called()


@pytest.mark.asyncio
async def test_idempotency_recovery_no_duplicate_trade():
    """If a trade already exists, it is recovered without creating a duplicate."""
    decision = make_decision(mode="paper")
    existing_trade = make_trade(trade_decision_id=decision.id, mode="paper")

    engine, mocks, bot, us, acc, snap = _make_engine_with_mocks(decision)
    mock_execute = AsyncMock()
    mock_recover = AsyncMock()

    with (
        patch.object(engine._platform_repo, "get", mocks["platform_settings_get"]),
        patch.object(engine._bot_repo, "get_bot", mocks["get_bot"]),
        patch.object(engine._bot_repo, "get_user_settings", mocks["get_user_settings"]),
        patch.object(engine._bot_repo, "get_exchange_account", mocks["get_exchange_account"]),
        patch.object(engine._market_data, "get_snapshot", mocks["get_snapshot"]),
        patch.object(engine._decision_repo, "count_critical_security_events",
                     mocks["count_critical_security_events"]),
        patch.object(engine._idempotency, "find_existing_trade",
                     AsyncMock(return_value=existing_trade)),
        patch.object(engine._recovery, "recover_existing_trade", mock_recover),
        patch.object(engine._notifications, "trade_executed", AsyncMock()),
        patch.object(engine._paper_executor, "execute", mock_execute),
        patch.object(engine._decision_repo, "mark_executed", mocks["mark_executed"]),
        patch.object(engine._decision_repo, "mark_failed", mocks["mark_failed"]),
        patch.object(engine._decision_repo, "mark_skipped", mocks["mark_skipped"]),
    ):
        await engine.run(decision)

    # Paper executor should NOT be called — trade already existed
    mock_execute.assert_not_called()
    # Recovery should have been invoked
    mock_recover.assert_called_once()


@pytest.mark.asyncio
async def test_risk_guard_block_skips_decision():
    """When risk guard blocks, decision is skipped and risk_log is written."""
    decision = make_decision(
        mode="paper",
        # Symbol not in bot.trading_pairs will cause risk guard to block
    )
    bot = make_bot(trading_pairs=["ETH/USDT"])  # BTC/USDT not allowed

    engine = ExecutionEngine()
    expected_trade = make_trade(mode="paper")
    mock_execute = AsyncMock(return_value=expected_trade)
    risk_log_mock = AsyncMock()
    skip_mock = AsyncMock()

    with (
        patch.object(engine._platform_repo, "get", AsyncMock(return_value=PlatformSettings())),
        patch.object(engine._bot_repo, "get_bot", AsyncMock(return_value=bot)),
        patch.object(engine._bot_repo, "get_user_settings",
                     AsyncMock(return_value=make_user_settings())),
        patch.object(engine._bot_repo, "get_exchange_account",
                     AsyncMock(return_value=make_exchange_account())),
        patch.object(engine._market_data, "get_snapshot",
                     AsyncMock(return_value=make_market_snapshot())),
        patch.object(engine._decision_repo, "count_critical_security_events",
                     AsyncMock(return_value=0)),
        patch.object(engine._bot_repo, "count_open_trades", AsyncMock(return_value=0)),
        patch.object(engine._idempotency, "find_existing_trade", AsyncMock(return_value=None)),
        patch.object(engine._risk_log, "create", risk_log_mock),
        patch.object(engine._decision_repo, "mark_skipped", skip_mock),
        patch.object(engine._decision_repo, "mark_failed", AsyncMock()),
        patch.object(engine._decision_repo, "mark_executed", AsyncMock()),
        patch.object(engine._notifications, "trade_skipped", AsyncMock()),
        patch.object(engine._paper_executor, "execute", mock_execute),
    ):
        await engine.run(decision)

    skip_mock.assert_called_once()
    risk_log_mock.assert_called_once()
    mock_execute.assert_not_called()


@pytest.mark.asyncio
async def test_shadow_mode_routes_to_shadow_executor():
    """Shadow decisions must be routed to ShadowExecutor."""
    decision = make_decision(mode="shadow", final_decision="open_long", approval_status="auto_approved")
    bot = make_bot(mode="shadow")
    engine = ExecutionEngine()
    expected_trade = make_trade(mode="shadow")

    with (
        patch.object(engine._bot_repo, "get_bot", AsyncMock(return_value=bot)),
        patch.object(engine._bot_repo, "get_user_settings",
                     AsyncMock(return_value=make_user_settings())),
        patch.object(engine._bot_repo, "get_exchange_account",
                     AsyncMock(return_value=make_exchange_account())),
        patch.object(engine._market_data, "get_snapshot",
                     AsyncMock(return_value=make_market_snapshot())),
        patch.object(engine._decision_repo, "count_critical_security_events",
                     AsyncMock(return_value=0)),
        patch.object(engine._bot_repo, "count_open_trades", AsyncMock(return_value=0)),
        patch.object(engine._idempotency, "find_existing_trade", AsyncMock(return_value=None)),
        patch.object(engine._shadow_executor, "execute",
                     AsyncMock(return_value=expected_trade)) as shadow_mock,
        patch.object(engine._paper_executor, "execute", AsyncMock()) as paper_mock,
        patch.object(engine._decision_repo, "mark_executed", AsyncMock()),
        patch.object(engine._audit_log, "create", AsyncMock()),
        patch.object(engine._notifications, "trade_executed", AsyncMock()),
        patch.object(engine._decision_repo, "mark_failed", AsyncMock()),
        patch.object(engine._decision_repo, "mark_skipped", AsyncMock()),
    ):
        await engine.run(decision)

    shadow_mock.assert_called_once()
    paper_mock.assert_not_called()


@pytest.mark.asyncio
async def test_unhandled_exception_calls_mark_failed():
    """Any unexpected exception must result in mark_failed."""
    decision = make_decision(mode="paper")
    engine = ExecutionEngine()

    with (
        patch.object(engine._bot_repo, "get_bot", AsyncMock(side_effect=RuntimeError("db down"))),
        patch.object(engine._decision_repo, "mark_failed", AsyncMock()) as fail_mock,
        patch.object(engine._decision_repo, "mark_skipped", AsyncMock()),
        patch.object(engine._notifications, "trade_failed", AsyncMock()),
    ):
        await engine.run(decision)

    fail_mock.assert_called_once()
    call_args = fail_mock.call_args
    assert decision.id == call_args[0][0]


@pytest.mark.asyncio
async def test_pipeline_never_creates_trade_on_security_block():
    """Guard safety invariant: no trade row is written when security guard blocks."""
    decision = make_decision(veto_summary={"vetoed": True})
    engine = ExecutionEngine()

    trade_repo_create = AsyncMock()

    with (
        patch.object(engine._bot_repo, "get_bot", AsyncMock(return_value=make_bot())),
        patch.object(engine._bot_repo, "get_user_settings",
                     AsyncMock(return_value=make_user_settings())),
        patch.object(engine._bot_repo, "get_exchange_account",
                     AsyncMock(return_value=make_exchange_account())),
        patch.object(engine._market_data, "get_snapshot",
                     AsyncMock(return_value=make_market_snapshot())),
        patch.object(engine._decision_repo, "count_critical_security_events",
                     AsyncMock(return_value=0)),
        patch.object(engine._decision_repo, "mark_skipped", AsyncMock()),
        patch.object(engine._decision_repo, "mark_failed", AsyncMock()),
        patch.object(engine._security_log, "create", AsyncMock()),
        patch.object(engine._notifications, "trade_skipped", AsyncMock()),
        patch("src.db.repositories.TradeRepository.create", trade_repo_create),
    ):
        await engine.run(decision)

    trade_repo_create.assert_not_called()
