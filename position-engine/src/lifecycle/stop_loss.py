"""
Stop-loss trigger check.

Long:  trigger if latest_price <= stop_loss
Short: trigger if latest_price >= stop_loss

Returns CLOSE_STOP_LOSS if triggered, HOLD otherwise.
"""
from __future__ import annotations

from src.db.models import Trade
from src.lifecycle.action import ActionType, LifecycleAction, hold


def check_stop_loss(trade: Trade, current_price: float) -> LifecycleAction:
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

    triggered = False

    if trade.is_long:
        triggered = current_price <= trade.stop_loss
    else:  # short
        triggered = current_price >= trade.stop_loss

    if not triggered:
        return hold()

    entry_price = trade.effective_entry_price
    stop_distance = abs(entry_price - trade.stop_loss) if entry_price > 0 else 0.0
    stop_distance_pct = (stop_distance / entry_price) * 100.0 if entry_price > 0 else None
    price_move = current_price - entry_price
    if not trade.is_long:
        price_move = entry_price - current_price
    price_move_pct = (price_move / entry_price) * 100.0 if entry_price > 0 else None
    comparator = "<=" if trade.is_long else ">="

    return LifecycleAction(
        action_type=ActionType.CLOSE_STOP_LOSS,
        reason=(
            f"Stop-loss triggered: price {current_price} "
            f"{comparator} "
            f"stop_loss {trade.stop_loss} "
            f"({'long' if trade.is_long else 'short'})"
        ),
        close_price=current_price,
        metadata={
            "stop_loss":          trade.stop_loss,
            "current_price":      current_price,
            "entry_price":        entry_price,
            "direction":          trade.direction,
            "trigger_rule":       f"current_price {comparator} stop_loss",
            "stop_distance":      stop_distance,
            "stop_distance_pct":  stop_distance_pct,
            "price_move_pct":     price_move_pct,
            "protection_reason":  "Configured stop-loss level was reached; position closed to cap downside risk.",
        },
    )
