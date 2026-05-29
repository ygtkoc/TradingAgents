"""
Stop-loss trigger check.

Long:  trigger if latest_price <= stop_loss
Short: trigger if latest_price >= stop_loss

Returns CLOSE_STOP_LOSS if triggered, HOLD otherwise.
"""
from __future__ import annotations

from src.db.models import Trade
from src.lifecycle.action import ActionType, LifecycleAction, hold


def check_stop_loss(
    trade: Trade,
    current_price: float,
    *,
    high_price: float | None = None,
    low_price: float | None = None,
) -> LifecycleAction:
    """
    Evaluate stop-loss trigger for an open trade.

    Args:
        trade:         The open trade.
        current_price: Latest market price.

    Returns:
        CLOSE_STOP_LOSS if triggered; HOLD otherwise.
    """
    if trade.stop_loss is None:
        return hold()

    high = high_price if high_price and high_price > 0 else current_price
    low = low_price if low_price and low_price > 0 else current_price

    if trade.is_long:
        current_triggered = current_price <= trade.stop_loss
        range_triggered = low <= trade.stop_loss
        trigger_price = current_price if current_triggered else trade.stop_loss
        trigger_observed_price = current_price if current_triggered else low
    else:  # short
        current_triggered = current_price >= trade.stop_loss
        range_triggered = high >= trade.stop_loss
        trigger_price = current_price if current_triggered else trade.stop_loss
        trigger_observed_price = current_price if current_triggered else high

    triggered = current_triggered or range_triggered

    if not triggered:
        return hold()

    entry_price = trade.effective_entry_price
    stop_distance = abs(entry_price - trade.stop_loss) if entry_price > 0 else 0.0
    stop_distance_pct = (stop_distance / entry_price) * 100.0 if entry_price > 0 else None
    price_move = trigger_price - entry_price
    if not trade.is_long:
        price_move = entry_price - trigger_price
    price_move_pct = (price_move / entry_price) * 100.0 if entry_price > 0 else None
    comparator = "<=" if trade.is_long else ">="
    trigger_source = "current_price" if current_triggered else "candle_range"

    return LifecycleAction(
        action_type=ActionType.CLOSE_STOP_LOSS,
        reason=(
            f"Stop-loss triggered: price {trigger_observed_price} "
            f"{comparator} "
            f"stop_loss {trade.stop_loss} "
            f"({'long' if trade.is_long else 'short'})"
        ),
        close_price=trigger_price,
        metadata={
            "stop_loss":          trade.stop_loss,
            "current_price":      current_price,
            "trigger_price":      trigger_price,
            "trigger_observed_price": trigger_observed_price,
            "trigger_source":     trigger_source,
            "high_price":         high,
            "low_price":          low,
            "entry_price":        entry_price,
            "direction":          trade.direction,
            "trigger_rule":       f"{trigger_source} {comparator} stop_loss",
            "stop_distance":      stop_distance,
            "stop_distance_pct":  stop_distance_pct,
            "price_move_pct":     price_move_pct,
            "protection_reason":  "Configured stop-loss level was reached; position closed to cap downside risk.",
        },
    )
