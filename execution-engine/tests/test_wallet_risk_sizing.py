import pytest

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
