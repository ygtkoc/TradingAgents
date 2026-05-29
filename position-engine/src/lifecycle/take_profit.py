"""
Take-profit trigger check.

Long:  trigger if latest_price >= take_profit
Short: trigger if latest_price <= take_profit

Returns CLOSE_TAKE_PROFIT if triggered, HOLD otherwise.
"""
from __future__ import annotations

from src.db.models import Trade
from src.lifecycle.action import ActionType, LifecycleAction, hold


def check_take_profit(
    trade: Trade,
    current_price: float,
    *,
    high_price: float | None = None,
    low_price: float | None = None,
) -> LifecycleAction:
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

    high = high_price if high_price and high_price > 0 else current_price
    low = low_price if low_price and low_price > 0 else current_price

    if trade.is_long:
        current_triggered = current_price >= trade.take_profit
        range_triggered = high >= trade.take_profit
        trigger_price = current_price if current_triggered else trade.take_profit
        trigger_observed_price = current_price if current_triggered else high
    else:  # short
        current_triggered = current_price <= trade.take_profit
        range_triggered = low <= trade.take_profit
        trigger_price = current_price if current_triggered else trade.take_profit
        trigger_observed_price = current_price if current_triggered else low

    triggered = current_triggered or range_triggered

    if not triggered:
        return hold()
    trigger_source = "current_price" if current_triggered else "candle_range"

    return LifecycleAction(
        action_type=ActionType.CLOSE_TAKE_PROFIT,
        reason=(
            f"Take-profit triggered: price {trigger_observed_price} "
            f"{'>=' if trade.is_long else '<='} "
            f"take_profit {trade.take_profit} "
            f"({'long' if trade.is_long else 'short'})"
        ),
        close_price=trigger_price,
        metadata={
            "take_profit":      trade.take_profit,
            "current_price":    current_price,
            "trigger_price":    trigger_price,
            "trigger_observed_price": trigger_observed_price,
            "trigger_source":   trigger_source,
            "high_price":       high,
            "low_price":        low,
            "direction":        trade.direction,
        },
    )
