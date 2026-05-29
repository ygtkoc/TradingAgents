import pytest
from unittest.mock import AsyncMock

from src.execution.engine import ExecutionEngine
from tests.conftest import make_bot, make_decision, make_market_snapshot


def test_enrich_sizing_makes_one_r_equal_wallet_risk_percent():
    engine = ExecutionEngine.__new__(ExecutionEngine)
    bot = make_bot(
        max_position_size_pct=5.0,
        risk_model="percentage",
        risk_value=2.0,
        risk_per_trade_pct=1.0,
        metadata={"trading_system": "futures_trading", "stop_loss_pct": 2.0},
    )
    decision = make_decision(risk_summary={"risk_reward_ratio": 2.0})
    snapshot = make_market_snapshot(close_price=100.0)

    engine._enrich_missing_risk_summary(
        decision=decision,
        bot=bot,
        market_snapshot=snapshot,
        portfolio_value_usd=1_000.0,
    )

    risk = decision.risk_summary

    assert risk["entry_price"] == pytest.approx(100.0)
    assert risk["stop_loss"] == pytest.approx(98.0)
    assert risk["quantity"] == pytest.approx(10.0, rel=1e-3)
    assert risk["risk_amount"] == pytest.approx(20.0, rel=1e-3)
    assert risk["risk_percent"] == pytest.approx(2.0, rel=1e-3)


def test_enrich_sizing_uses_max_leverage_for_margin_metadata():
    engine = ExecutionEngine.__new__(ExecutionEngine)
    bot = make_bot(
        risk_model="percentage",
        risk_value=10.0,
        metadata={"trading_system": "futures_trading", "stop_loss_pct": 1.0},
    )
    decision = make_decision(risk_summary={"risk_reward_ratio": 2.0})
    snapshot = make_market_snapshot(close_price=100.0)

    engine._enrich_missing_risk_summary(
        decision=decision,
        bot=bot,
        market_snapshot=snapshot,
        portfolio_value_usd=1_000.0,
        max_leverage=20.0,
    )

    risk = decision.risk_summary

    assert risk["quantity"] == pytest.approx(100.0, rel=1e-3)
    assert risk["notional"] == pytest.approx(10_000.0, rel=1e-3)
    assert risk["leverage"] == pytest.approx(20.0)
    assert risk["margin_required"] == pytest.approx(500.0, rel=1e-3)
    assert risk["risk_amount"] == pytest.approx(100.0, rel=1e-3)
    assert risk["risk_percent"] == pytest.approx(10.0, rel=1e-3)


@pytest.mark.asyncio
async def test_paper_portfolio_value_uses_actual_account_balance():
    engine = ExecutionEngine.__new__(ExecutionEngine)
    engine._paper_account = AsyncMock()
    engine._paper_account.get_account = AsyncMock(
        return_value={"balance": 1_000.0, "starting_balance": 10_000.0}
    )

    value = await engine._get_portfolio_value(
        exchange_account=None,
        user_settings=None,
        market_snapshot=None,
        decision=make_decision(mode="paper"),
        execution_mode="paper",
    )

    assert value == pytest.approx(1_000.0)


@pytest.mark.asyncio
async def test_paper_portfolio_value_fails_closed_without_account():
    engine = ExecutionEngine.__new__(ExecutionEngine)
    engine._paper_account = AsyncMock()
    engine._paper_account.get_account = AsyncMock(return_value=None)

    value = await engine._get_portfolio_value(
        exchange_account=None,
        user_settings=None,
        market_snapshot=None,
        decision=make_decision(mode="paper"),
        execution_mode="paper",
    )

    assert value == 0.0
