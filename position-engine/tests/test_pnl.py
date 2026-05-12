"""
Tests for P&L calculation (pnl.py).

Covers:
  - Long unrealized P&L (profit and loss cases)
  - Short unrealized P&L (profit and loss cases)
  - Long realized P&L on close
  - Short realized P&L on close
  - Edge cases: zero quantity, zero price, negative price guards
  - Fees are passed through correctly
  - P&L percentage helper
"""
import pytest

from src.lifecycle.pnl import (
    calculate_realized_pnl,
    calculate_unrealized_pnl,
    pnl_percentage,
)
from tests.conftest import make_trade


# ── Unrealized P&L ─────────────────────────────────────────────────────────────

class TestUnrealizedPnlLong:
    """Long position: profit when price rises, loss when price falls."""

    def _trade(self, entry=50_000.0, qty=1.0, **kw):
        return make_trade(direction="long", entry_price=entry, quantity=qty, **kw)

    def test_profit_when_price_rises(self):
        trade = self._trade(entry=50_000.0, qty=1.0)
        pnl = calculate_unrealized_pnl(trade, current_price=55_000.0)
        assert pnl == pytest.approx(5_000.0)

    def test_loss_when_price_falls(self):
        trade = self._trade(entry=50_000.0, qty=1.0)
        pnl = calculate_unrealized_pnl(trade, current_price=45_000.0)
        assert pnl == pytest.approx(-5_000.0)

    def test_zero_pnl_at_entry_price(self):
        trade = self._trade(entry=50_000.0, qty=1.0)
        pnl = calculate_unrealized_pnl(trade, current_price=50_000.0)
        assert pnl == pytest.approx(0.0)

    def test_quantity_scaling(self):
        trade = self._trade(entry=100.0, qty=0.5)
        pnl = calculate_unrealized_pnl(trade, current_price=200.0)
        assert pnl == pytest.approx(50.0)  # (200-100)*0.5

    def test_fees_reduce_pnl(self):
        trade = self._trade(entry=50_000.0, qty=1.0)
        pnl = calculate_unrealized_pnl(trade, current_price=55_000.0, fees=100.0)
        assert pnl == pytest.approx(4_900.0)

    def test_uses_avg_fill_price_over_entry_price(self):
        """avg_fill_price takes precedence over entry_price in calculation."""
        trade = make_trade(
            direction="long",
            entry_price=50_000.0,
            avg_fill_price=49_000.0,
            quantity=1.0,
        )
        # Should use avg_fill_price=49_000 as effective entry
        pnl = calculate_unrealized_pnl(trade, current_price=50_000.0)
        assert pnl == pytest.approx(1_000.0)

    def test_uses_filled_quantity_over_quantity(self):
        trade = make_trade(
            direction="long",
            entry_price=100.0,
            quantity=10.0,
            filled_quantity=5.0,
        )
        pnl = calculate_unrealized_pnl(trade, current_price=200.0)
        assert pnl == pytest.approx(500.0)  # (200-100)*5.0

    def test_zero_price_returns_zero(self):
        trade = self._trade()
        assert calculate_unrealized_pnl(trade, current_price=0.0) == 0.0

    def test_zero_quantity_returns_zero(self):
        trade = self._trade(qty=0.0)
        assert calculate_unrealized_pnl(trade, current_price=55_000.0) == 0.0


class TestUnrealizedPnlShort:
    """Short position: profit when price falls, loss when price rises."""

    def _trade(self, entry=50_000.0, qty=1.0, **kw):
        return make_trade(direction="short", side="sell", entry_price=entry, quantity=qty, **kw)

    def test_profit_when_price_falls(self):
        trade = self._trade(entry=50_000.0, qty=1.0)
        pnl = calculate_unrealized_pnl(trade, current_price=45_000.0)
        assert pnl == pytest.approx(5_000.0)

    def test_loss_when_price_rises(self):
        trade = self._trade(entry=50_000.0, qty=1.0)
        pnl = calculate_unrealized_pnl(trade, current_price=55_000.0)
        assert pnl == pytest.approx(-5_000.0)

    def test_zero_pnl_at_entry_price(self):
        trade = self._trade(entry=50_000.0, qty=1.0)
        pnl = calculate_unrealized_pnl(trade, current_price=50_000.0)
        assert pnl == pytest.approx(0.0)

    def test_fees_reduce_short_pnl(self):
        trade = self._trade(entry=50_000.0, qty=1.0)
        pnl = calculate_unrealized_pnl(trade, current_price=45_000.0, fees=200.0)
        assert pnl == pytest.approx(4_800.0)


# ── Realized P&L ───────────────────────────────────────────────────────────────

class TestRealizedPnlLong:
    def _trade(self, entry=50_000.0, qty=1.0):
        return make_trade(direction="long", entry_price=entry, quantity=qty)

    def test_profit_on_close_above_entry(self):
        trade = self._trade(entry=50_000.0, qty=1.0)
        pnl = calculate_realized_pnl(trade, exit_price=60_000.0)
        assert pnl == pytest.approx(10_000.0)

    def test_loss_on_close_below_entry(self):
        trade = self._trade(entry=50_000.0, qty=1.0)
        pnl = calculate_realized_pnl(trade, exit_price=40_000.0)
        assert pnl == pytest.approx(-10_000.0)

    def test_zero_pnl_at_entry(self):
        trade = self._trade(entry=50_000.0)
        assert calculate_realized_pnl(trade, exit_price=50_000.0) == pytest.approx(0.0)

    def test_zero_exit_price_returns_zero(self):
        trade = self._trade()
        assert calculate_realized_pnl(trade, exit_price=0.0) == 0.0


class TestRealizedPnlShort:
    def _trade(self, entry=50_000.0, qty=1.0):
        return make_trade(direction="short", side="sell", entry_price=entry, quantity=qty)

    def test_profit_on_close_below_entry(self):
        trade = self._trade(entry=50_000.0, qty=1.0)
        pnl = calculate_realized_pnl(trade, exit_price=40_000.0)
        assert pnl == pytest.approx(10_000.0)

    def test_loss_on_close_above_entry(self):
        trade = self._trade(entry=50_000.0, qty=1.0)
        pnl = calculate_realized_pnl(trade, exit_price=60_000.0)
        assert pnl == pytest.approx(-10_000.0)


# ── P&L Percentage ─────────────────────────────────────────────────────────────

class TestPnlPercentage:
    def test_profit_percentage(self):
        pct = pnl_percentage(pnl=1_000.0, entry_price=50_000.0, quantity=1.0)
        assert pct == pytest.approx(2.0)

    def test_loss_percentage(self):
        pct = pnl_percentage(pnl=-2_500.0, entry_price=50_000.0, quantity=1.0)
        assert pct == pytest.approx(-5.0)

    def test_zero_position_value_returns_zero(self):
        assert pnl_percentage(pnl=1_000.0, entry_price=0.0, quantity=1.0) == 0.0
        assert pnl_percentage(pnl=1_000.0, entry_price=100.0, quantity=0.0) == 0.0
