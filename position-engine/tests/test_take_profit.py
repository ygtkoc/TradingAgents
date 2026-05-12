"""
Tests for take-profit trigger logic (take_profit.py).

Covers:
  - Long: triggers when price >= take_profit
  - Long: does NOT trigger when price < take_profit
  - Short: triggers when price <= take_profit
  - Short: does NOT trigger when price > take_profit
  - No take_profit set → HOLD
  - Boundary values (price exactly at take_profit)
  - Returned action has correct type, reason, and metadata
"""
import pytest

from src.lifecycle.action import ActionType
from src.lifecycle.take_profit import check_take_profit
from tests.conftest import make_trade


class TestTakeProfitLong:
    """Long position: take-profit triggers when price rises to or above the target."""

    def test_triggers_when_price_at_target(self):
        trade = make_trade(direction="long", entry_price=50_000.0, take_profit=60_000.0)
        action = check_take_profit(trade, current_price=60_000.0)
        assert action.action_type == ActionType.CLOSE_TAKE_PROFIT

    def test_triggers_when_price_above_target(self):
        trade = make_trade(direction="long", entry_price=50_000.0, take_profit=60_000.0)
        action = check_take_profit(trade, current_price=61_000.0)
        assert action.action_type == ActionType.CLOSE_TAKE_PROFIT

    def test_does_not_trigger_when_price_below_target(self):
        trade = make_trade(direction="long", entry_price=50_000.0, take_profit=60_000.0)
        action = check_take_profit(trade, current_price=59_000.0)
        assert action.action_type == ActionType.HOLD

    def test_close_price_is_current_price(self):
        trade = make_trade(direction="long", take_profit=60_000.0)
        action = check_take_profit(trade, current_price=62_000.0)
        assert action.close_price == pytest.approx(62_000.0)

    def test_metadata_contains_target_and_price(self):
        trade = make_trade(direction="long", take_profit=60_000.0)
        action = check_take_profit(trade, current_price=60_500.0)
        assert action.metadata["take_profit"] == 60_000.0
        assert action.metadata["current_price"] == 60_500.0
        assert action.metadata["direction"] == "long"

    def test_no_take_profit_returns_hold(self):
        trade = make_trade(direction="long", take_profit=None)
        assert check_take_profit(trade, current_price=99_000.0).action_type == ActionType.HOLD

    def test_price_one_tick_below_target_does_not_trigger(self):
        trade = make_trade(direction="long", take_profit=60_000.0)
        action = check_take_profit(trade, current_price=59_999.99)
        assert action.action_type == ActionType.HOLD


class TestTakeProfitShort:
    """Short position: take-profit triggers when price falls to or below the target."""

    def _trade(self, take_profit=40_000.0):
        return make_trade(direction="short", side="sell", entry_price=50_000.0, take_profit=take_profit)

    def test_triggers_when_price_at_target(self):
        trade = self._trade(take_profit=40_000.0)
        action = check_take_profit(trade, current_price=40_000.0)
        assert action.action_type == ActionType.CLOSE_TAKE_PROFIT

    def test_triggers_when_price_below_target(self):
        trade = self._trade(take_profit=40_000.0)
        action = check_take_profit(trade, current_price=39_000.0)
        assert action.action_type == ActionType.CLOSE_TAKE_PROFIT

    def test_does_not_trigger_when_price_above_target(self):
        trade = self._trade(take_profit=40_000.0)
        action = check_take_profit(trade, current_price=41_000.0)
        assert action.action_type == ActionType.HOLD

    def test_metadata_contains_direction(self):
        trade = self._trade(take_profit=40_000.0)
        action = check_take_profit(trade, current_price=39_000.0)
        assert action.metadata["direction"] == "short"

    def test_price_one_tick_above_target_does_not_trigger(self):
        trade = self._trade(take_profit=40_000.0)
        action = check_take_profit(trade, current_price=40_000.01)
        assert action.action_type == ActionType.HOLD
