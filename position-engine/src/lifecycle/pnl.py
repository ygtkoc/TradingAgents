"""
P&L calculation for the Position Engine.

Unrealized P&L:
  Long:  (current_price - avg_entry_price) * quantity - fees
  Short: (avg_entry_price - current_price) * quantity - fees

Realized P&L (on close):
  Long:  (exit_price - avg_entry_price) * quantity - fees
  Short: (avg_entry_price - exit_price) * quantity - fees

Fees placeholder — currently 0.0.
TODO: integrate exchange fee schedules (maker/taker) for accurate P&L.
"""
from __future__ import annotations

from src.db.models import Trade


def calculate_unrealized_pnl(
    trade: Trade,
    current_price: float,
    fees: float = 0.0,
) -> float:
    """
    Calculate unrealized P&L for an open trade at current_price.

    Args:
        trade:         The open trade.
        current_price: Latest market price.
        fees:          Estimated fees (default 0.0 until fee schedule integrated).

    Returns:
        Signed P&L in quote currency. Positive = profit.
    """
    qty   = trade.effective_quantity
    entry = trade.effective_entry_price

    if qty <= 0 or entry <= 0 or current_price <= 0:
        return 0.0

    if trade.is_long:
        return (current_price - entry) * qty - fees
    else:
        return (entry - current_price) * qty - fees


def calculate_realized_pnl(
    trade: Trade,
    exit_price: float,
    fees: float = 0.0,
) -> float:
    """
    Calculate realized P&L when a trade is closed at exit_price.

    Args:
        trade:      The trade being closed.
        exit_price: The actual fill price of the close order.
        fees:       Exchange fees (default 0.0).

    Returns:
        Signed realized P&L. Positive = profit.
    """
    qty   = trade.effective_quantity
    entry = trade.effective_entry_price

    if qty <= 0 or entry <= 0 or exit_price <= 0:
        return 0.0

    if trade.is_long:
        return (exit_price - entry) * qty - fees
    else:
        return (entry - exit_price) * qty - fees


def pnl_percentage(pnl: float, entry_price: float, quantity: float) -> float:
    """Return P&L as a percentage of the initial position value."""
    position_value = entry_price * quantity
    if position_value <= 0:
        return 0.0
    return (pnl / position_value) * 100.0
