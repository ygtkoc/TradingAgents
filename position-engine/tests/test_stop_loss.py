"""
Tests for stop-loss trigger logic (stop_loss.py).

Covers:
  - Long: triggers when price <= stop_loss
  - Long: does NOT trigger when price > stop_loss
  - Short: triggers when price >= stop_loss
  - Short: does NOT trigger when price < stop_loss
  - No stop_loss set → HOLD
  - Boundary values (price exactly at stop_loss)
  - Returned action has correct type, reason, and metadata
"""
import pytest

from src.lifecycle.action import ActionType
from src.lifecycle.stop_loss import check_stop_loss
from tests.conftest import make_trade


class TestStopLossLong:
    """Long position: stop-loss triggers when price falls to or below the level."""

    def test_triggers_when_price_at_stop(self):
        trade = make_trade(direction="long", entry_price=50_000.0, stop_loss=48_000.0)
        action = check_stop_loss(trade, current_price=48_000.0)
        assert action.action_type == ActionType.CLOSE_STOP_LOSS

    def test_triggers_when_price_below_stop(self):
        trade = make_trade(direction="long", entry_price=50_000.0, stop_loss=48_000.0)
        action = check_stop_loss(trade, current_price=47_500.0)
        assert action.action_type == ActionType.CLOSE_STOP_LOSS

    def test_does_not_trigger_when_price_above_stop(self):
        trade = make_trade(direction="long", entry_price=50_000.0, stop_loss=48_000.0)
        action = check_stop_loss(trade, current_price=49_000.0)
        assert action.action_type == ActionType.HOLD

    def test_close_price_is_current_price(self):
        trade = make_trade(direction="long", entry_price=50_000.0, stop_loss=48_000.0)
        action = check_stop_loss(trade, current_price=47_000.0)
        assert action.close_price == pytest.approx(47_000.0)

    def test_metadata_contains_stop_level(self):
        trade = make_trade(direction="long", entry_price=50_000.0, stop_loss=48_000.0)
        action = check_stop_loss(trade, current_price=47_000.0)
        assert action.metadata["stop_loss"] == 48_000.0
        assert action.metadata["current_price"] == 47_000.0
        assert action.metadata["direction"] == "long"

    def test_reason_mentions_direction(self):
        trade = make_trade(direction="long", entry_price=50_000.0, stop_loss=48_000.0)
        action = check_stop_loss(trade, current_price=47_000.0)
        assert "long" in action.reason.lower() or "<=" in action.reason

    def test_no_stop_loss_returns_hold(self):
        trade = make_trade(direction="long", stop_loss=None)
        assert check_stop_loss(trade, current_price=40_000.0).action_type == ActionType.HOLD

    def test_price_one_tick_above_stop_does_not_trigger(self):
        trade = make_trade(direction="long", stop_loss=48_000.0)
        action = check_stop_loss(trade, current_price=48_000.01)
        assert action.action_type == ActionType.HOLD


class TestStopLossShort:
    """Short position: stop-loss triggers when price rises to or above the level."""

    def _trade(self, stop_loss=52_000.0):
        return make_trade(direction="short", side="sell", entry_price=50_000.0, stop_loss=stop_loss)

    def test_triggers_when_price_at_stop(self):
        trade = self._trade(stop_loss=52_000.0)
        action = check_stop_loss(trade, current_price=52_000.0)
        assert action.action_type == ActionType.CLOSE_STOP_LOSS

    def test_triggers_when_price_above_stop(self):
        trade = self._trade(stop_loss=52_000.0)
        action = check_stop_loss(trade, current_price=53_000.0)
        assert action.action_type == ActionType.CLOSE_STOP_LOSS

    def test_does_not_trigger_when_price_below_stop(self):
        trade = self._trade(stop_loss=52_000.0)
        action = check_stop_loss(trade, current_price=51_000.0)
        assert action.action_type == ActionType.HOLD

    def test_close_price_is_current_price(self):
        trade = self._trade(stop_loss=52_000.0)
        action = check_stop_loss(trade, current_price=53_000.0)
        assert action.close_price == pytest.approx(53_000.0)

    def test_metadata_contains_direction(self):
        trade = self._trade(stop_loss=52_000.0)
        action = check_stop_loss(trade, current_price=53_000.0)
        assert action.metadata["direction"] == "short"

    def test_price_one_tick_below_stop_does_not_trigger(self):
        trade = self._trade(stop_loss=52_000.0)
        action = check_stop_loss(trade, current_price=51_999.99)
        assert action.action_type == ActionType.HOLD
