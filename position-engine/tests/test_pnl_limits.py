"""
Tests for PnL-denominated stop-loss and take-profit backstops.
"""
import pytest

from src.lifecycle.action import ActionType
from src.lifecycle.pnl_limits import check_pnl_stop_loss, check_pnl_take_profit
from tests.conftest import make_trade


class TestPnlStopLoss:
    def test_triggers_when_loss_reaches_risk_amount(self):
        trade = make_trade(risk_amount=19.50)
        action = check_pnl_stop_loss(trade, current_price=49_765.0, unrealized_pnl=-23.0)
        assert action.action_type == ActionType.CLOSE_STOP_LOSS
        assert action.close_price == pytest.approx(49_765.0)
        assert action.metadata["risk_amount"] == pytest.approx(19.50)
        assert action.metadata["loss_limit"] == pytest.approx(-19.50)

    def test_does_not_trigger_before_loss_limit(self):
        trade = make_trade(risk_amount=19.50)
        action = check_pnl_stop_loss(trade, current_price=49_900.0, unrealized_pnl=-12.0)
        assert action.action_type == ActionType.HOLD

    def test_missing_risk_amount_holds(self):
        trade = make_trade(risk_amount=None)
        action = check_pnl_stop_loss(trade, current_price=49_700.0, unrealized_pnl=-23.0)
        assert action.action_type == ActionType.HOLD


class TestPnlTakeProfit:
    def test_triggers_when_profit_reaches_expected_reward(self):
        trade = make_trade(risk_amount=20.0, expected_reward=60.0)
        action = check_pnl_take_profit(trade, current_price=50_800.0, unrealized_pnl=80.0)
        assert action.action_type == ActionType.CLOSE_TAKE_PROFIT
        assert action.close_price == pytest.approx(50_800.0)
        assert action.metadata["expected_reward"] == pytest.approx(60.0)

    def test_uses_risk_reward_ratio_fallback(self):
        trade = make_trade(risk_amount=20.0, expected_reward=None, risk_reward_ratio=3.0)
        action = check_pnl_take_profit(trade, current_price=50_650.0, unrealized_pnl=65.0)
        assert action.action_type == ActionType.CLOSE_TAKE_PROFIT
        assert action.metadata["expected_reward"] == pytest.approx(60.0)

    def test_does_not_trigger_before_reward_target(self):
        trade = make_trade(risk_amount=20.0, expected_reward=60.0)
        action = check_pnl_take_profit(trade, current_price=50_400.0, unrealized_pnl=40.0)
        assert action.action_type == ActionType.HOLD
