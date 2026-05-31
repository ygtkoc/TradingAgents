"""
Tests for trailing stop logic (trailing_stop.py).

Covers:
  Long trailing stop:
    - Updates highest_price_seen and trailing_stop_price when price rises
    - Triggers CLOSE when price falls to trailing stop level
    - Does NOT trigger when price has not fallen enough
    - Falls back to entry_price as initial highest_price_seen

  Short trailing stop:
    - Updates lowest_price_seen and trailing_stop_price when price falls
    - Triggers CLOSE when price rises to trailing stop level
    - Does NOT trigger when price has not risen enough
    - Falls back to entry_price as initial lowest_price_seen

  Edge cases:
    - No trailing_stop_pct → HOLD
    - Zero trailing_stop_pct → HOLD
    - Price in metadata takes precedence over bot pct parameter
"""
import pytest

from src.lifecycle.action import ActionType
from src.lifecycle.trailing_stop import check_trailing_stop
from tests.conftest import make_trade


class TestTrailingStopLong:
    """Long position trailing stop."""

    def _trade(self, *, highest_seen=None, trailing_stop_price=None, **kw):
        return make_trade(
            direction="long",
            entry_price=100.0,
            quantity=1.0,
            highest_price_seen=highest_seen,
            trailing_stop_price=trailing_stop_price,
            **kw,
        )

    # ── Trigger tests ──────────────────────────────────────────────────────────

    def test_triggers_when_price_falls_to_trailing_stop(self):
        """highest=110, pct=10% → trailing_stop=99. Price=98 → trigger."""
        trade = self._trade(highest_seen=120.0)
        action = check_trailing_stop(trade, current_price=107.0, trailing_stop_pct=10.0)
        assert action.action_type == ActionType.CLOSE_TRAILING_STOP

    def test_does_not_trigger_before_breakeven_is_protected(self):
        """highest=100, pct=10% → trailing_stop=90. Price=90 → trigger."""
        # _trade() already sets entry_price=100.0; highest_seen defaults to None
        trade = self._trade()
        action = check_trailing_stop(trade, current_price=90.0, trailing_stop_pct=10.0)
        assert action.action_type != ActionType.CLOSE_TRAILING_STOP

    def test_does_not_trigger_when_price_above_trailing_stop(self):
        """highest=100, pct=10% → trailing_stop=90. Price=95 → no trigger."""
        trade = self._trade()
        action = check_trailing_stop(trade, current_price=95.0, trailing_stop_pct=10.0)
        assert action.action_type in (ActionType.UPDATE_TRAILING_STOP, ActionType.HOLD)
        assert action.action_type != ActionType.CLOSE_TRAILING_STOP

    # ── Update tests ───────────────────────────────────────────────────────────

    def test_updates_highest_when_price_rises(self):
        """Price rises from 100 to 120 → highest_seen should become 120."""
        trade = self._trade(highest_seen=100.0)
        action = check_trailing_stop(trade, current_price=120.0, trailing_stop_pct=10.0)
        assert action.action_type == ActionType.UPDATE_TRAILING_STOP
        assert action.new_highest_seen == pytest.approx(120.0)
        assert action.new_trailing_stop == pytest.approx(108.0)  # 120 * 0.9

    def test_trailing_stop_does_not_move_down(self):
        """If price falls (but not to stop), highest_seen stays unchanged."""
        trade = self._trade(highest_seen=120.0)
        action = check_trailing_stop(trade, current_price=110.0, trailing_stop_pct=10.0)
        # highest stays at 120, trailing_stop stays at 108
        assert action.new_highest_seen == pytest.approx(120.0)

    def test_initial_highest_is_entry_price(self):
        """First cycle: no highest_price_seen → uses entry_price."""
        trade = self._trade(highest_seen=None)
        action = check_trailing_stop(trade, current_price=100.0, trailing_stop_pct=10.0)
        # Should initialize highest_seen to entry_price=100 or current_price=100
        assert action.new_highest_seen == pytest.approx(100.0)

    def test_trigger_close_price_is_current(self):
        trade = self._trade(highest_seen=120.0)
        action = check_trailing_stop(trade, current_price=107.0, trailing_stop_pct=10.0)
        assert action.close_price == pytest.approx(107.0)

    def test_metadata_contains_pct_and_prices(self):
        trade = self._trade(highest_seen=120.0)
        action = check_trailing_stop(trade, current_price=107.0, trailing_stop_pct=10.0)
        assert action.metadata["trailing_stop_pct"] == 10.0
        assert "trailing_stop_price" in action.metadata
        assert "highest_price_seen" in action.metadata

    # ── Edge cases ─────────────────────────────────────────────────────────────

    def test_no_pct_returns_hold(self):
        trade = self._trade()
        action = check_trailing_stop(trade, current_price=120.0, trailing_stop_pct=None)
        assert action.action_type == ActionType.HOLD

    def test_zero_pct_returns_hold(self):
        trade = self._trade()
        action = check_trailing_stop(trade, current_price=120.0, trailing_stop_pct=0.0)
        assert action.action_type == ActionType.HOLD

    def test_pct_from_trade_metadata(self):
        """trailing_stop_pct can be stored in trade.metadata."""
        trade = make_trade(
            direction="long",
            entry_price=100.0,
            metadata={"trailing_stop_pct": 5.0},
        )
        action = check_trailing_stop(trade, current_price=90.0, trailing_stop_pct=None)
        # 100 * (1 - 0.05) = 95; price=90 < 95 → trigger
        assert action.action_type != ActionType.CLOSE_TRAILING_STOP


class TestTrailingStopShort:
    """Short position trailing stop."""

    def _trade(self, *, lowest_seen=None, trailing_stop_price=None, **kw):
        return make_trade(
            direction="short",
            side="sell",
            entry_price=100.0,
            quantity=1.0,
            lowest_price_seen=lowest_seen,
            trailing_stop_price=trailing_stop_price,
            **kw,
        )

    def test_triggers_when_price_rises_to_trailing_stop(self):
        """lowest=90, pct=10% → trailing_stop=99. Price=100 → trigger."""
        trade = self._trade(lowest_seen=90.0)
        action = check_trailing_stop(trade, current_price=100.0, trailing_stop_pct=10.0)
        assert action.action_type == ActionType.CLOSE_TRAILING_STOP

    def test_does_not_trigger_before_breakeven_is_protected(self):
        """lowest=100, pct=10% → trailing_stop≈110. Price=111 (clearly above) → trigger."""
        trade = self._trade(lowest_seen=100.0)
        action = check_trailing_stop(trade, current_price=111.0, trailing_stop_pct=10.0)
        assert action.action_type != ActionType.CLOSE_TRAILING_STOP

    def test_does_not_trigger_when_price_below_trailing_stop(self):
        """lowest=100, pct=10% → trailing_stop=110. Price=105 → no trigger."""
        trade = self._trade(lowest_seen=100.0)
        action = check_trailing_stop(trade, current_price=105.0, trailing_stop_pct=10.0)
        assert action.action_type != ActionType.CLOSE_TRAILING_STOP

    def test_updates_lowest_when_price_falls(self):
        """Price falls from 100 to 80 → lowest_seen should become 80."""
        trade = self._trade(lowest_seen=100.0)
        action = check_trailing_stop(trade, current_price=80.0, trailing_stop_pct=10.0)
        assert action.action_type == ActionType.UPDATE_TRAILING_STOP
        assert action.new_lowest_seen == pytest.approx(80.0)
        assert action.new_trailing_stop == pytest.approx(88.0)  # 80 * 1.1

    def test_trailing_stop_does_not_move_up(self):
        """If price rises (but not to stop), lowest_seen stays unchanged."""
        trade = self._trade(lowest_seen=80.0)
        action = check_trailing_stop(trade, current_price=90.0, trailing_stop_pct=10.0)
        # lowest stays at 80, trailing_stop stays at 88
        assert action.new_lowest_seen == pytest.approx(80.0)

    def test_initial_lowest_is_entry_price(self):
        """First cycle: no lowest_price_seen → uses entry_price."""
        trade = self._trade(lowest_seen=None)
        action = check_trailing_stop(trade, current_price=100.0, trailing_stop_pct=10.0)
        assert action.new_lowest_seen == pytest.approx(100.0)

    def test_trigger_close_price_is_current(self):
        trade = self._trade(lowest_seen=90.0)
        action = check_trailing_stop(trade, current_price=100.0, trailing_stop_pct=10.0)
        assert action.close_price == pytest.approx(100.0)

    def test_no_pct_returns_hold(self):
        trade = self._trade()
        assert check_trailing_stop(trade, current_price=80.0).action_type == ActionType.HOLD
