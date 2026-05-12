"""
Take-profit trigger check.

Long:  trigger if latest_price >= take_profit
Short: trigger if latest_price <= take_profit

Returns CLOSE_TAKE_PROFIT if triggered, HOLD otherwise.
"""
from __future__ import annotations

from src.db.models import Trade
from src.lifecycle.action import ActionType, LifecycleAction, hold


def check_take_profit(trade: Trade, current_price: float) -> LifecycleAction:
    """
    Evaluate take-profit trigger for an open trade.

    Args:
        trade:         The open trade.
        current_price: Latest market price.

    Returns:
        CLOSE_TAKE_PROFIT if triggered; HOLD otherwise.
    """
    if trade.take_profit is None:
        return hold()

    triggered = False

    if trade.is_long:
        triggered = current_price >= trade.take_profit
    else:  # short
        triggered = current_price <= trade.take_profit

    if not triggered:
        return hold()

    return LifecycleAction(
        action_type=ActionType.CLOSE_TAKE_PROFIT,
        reason=(
            f"Take-profit triggered: price {current_price} "
            f"{'>=' if trade.is_long else '<='} "
            f"take_profit {trade.take_profit} "
            f"({'long' if trade.is_long else 'short'})"
        ),
        close_price=current_price,
        metadata={
            "take_profit":   trade.take_profit,
            "current_price": current_price,
            "direction":     trade.direction,
        },
    )
