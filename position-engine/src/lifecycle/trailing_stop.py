"""
Trailing stop logic.

Long:
  - Track highest_price_seen = max(previous_highest, current_price)
  - trailing_stop_price = highest_price_seen * (1 - trailing_stop_pct / 100)
  - Trigger CLOSE if current_price <= trailing_stop_price

Short:
  - Track lowest_price_seen = min(previous_lowest, current_price)
  - trailing_stop_price = lowest_price_seen * (1 + trailing_stop_pct / 100)
  - Trigger CLOSE if current_price >= trailing_stop_price

Returns:
  CLOSE_TRAILING_STOP  — if triggered
  UPDATE_TRAILING_STOP — if price moved favorably (update tracking values)
  HOLD                 — no trailing stop configured or no update needed
"""
from __future__ import annotations

from typing import Optional

from src.db.models import Trade
from src.lifecycle.action import ActionType, LifecycleAction, hold


def check_trailing_stop(
    trade: Trade,
    current_price: float,
    trailing_stop_pct: Optional[float] = None,
) -> LifecycleAction:
    """
    Evaluate and update the trailing stop for an open trade.

    Args:
        trade:             The open trade.
        current_price:     Latest market price.
        trailing_stop_pct: Percentage distance for trailing stop.
                           If None, reads from trade.metadata.trailing_stop_pct.
                           If still None, returns HOLD.

    Returns:
        CLOSE_TRAILING_STOP, UPDATE_TRAILING_STOP, or HOLD.
    """
    pct = trailing_stop_pct or _get_pct(trade)
    if pct is None or pct <= 0:
        return hold()

    if trade.is_long:
        return _check_long(trade, current_price, pct)
    else:
        return _check_short(trade, current_price, pct)


def _get_pct(trade: Trade) -> Optional[float]:
    """Extract trailing_stop_pct from trade metadata."""
    meta = trade.metadata or {}
    val  = meta.get("trailing_stop_pct")
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _check_long(
    trade: Trade, current_price: float, pct: float
) -> LifecycleAction:
    # Update highest price seen
    previous_highest = trade.highest_price_seen or trade.effective_entry_price
    new_highest      = max(previous_highest, current_price)

    # Compute trailing stop price
    new_trailing_stop = new_highest * (1.0 - pct / 100.0)

    # Check trigger
    triggered = current_price <= new_trailing_stop

    if triggered:
        return LifecycleAction(
            action_type=ActionType.CLOSE_TRAILING_STOP,
            reason=(
                f"Trailing stop triggered (long): price {current_price:.6f} "
                f"<= trailing_stop {new_trailing_stop:.6f} "
                f"(highest_seen={new_highest:.6f}, pct={pct}%)"
            ),
            close_price=current_price,
            new_trailing_stop=new_trailing_stop,
            new_highest_seen=new_highest,
            metadata={
                "trailing_stop_pct":   pct,
                "highest_price_seen":  new_highest,
                "trailing_stop_price": new_trailing_stop,
                "current_price":       current_price,
                "direction":           "long",
            },
        )

    # No trigger — return update action if price moved
    price_moved = new_highest > previous_highest
    old_trailing = trade.trailing_stop_price or (
        previous_highest * (1.0 - pct / 100.0)
    )

    if price_moved or (trade.trailing_stop_price is None):
        return LifecycleAction(
            action_type=ActionType.UPDATE_TRAILING_STOP,
            reason=(
                f"Trailing stop updated (long): "
                f"highest={new_highest:.6f}, stop={new_trailing_stop:.6f}"
            ),
            new_trailing_stop=new_trailing_stop,
            new_highest_seen=new_highest,
            metadata={
                "trailing_stop_pct":   pct,
                "highest_price_seen":  new_highest,
                "trailing_stop_price": new_trailing_stop,
                "current_price":       current_price,
            },
        )

    return hold()


def _check_short(
    trade: Trade, current_price: float, pct: float
) -> LifecycleAction:
    # Update lowest price seen
    previous_lowest = trade.lowest_price_seen or trade.effective_entry_price
    new_lowest      = min(previous_lowest, current_price)

    # Compute trailing stop price
    new_trailing_stop = new_lowest * (1.0 + pct / 100.0)

    # Check trigger
    triggered = current_price >= new_trailing_stop

    if triggered:
        return LifecycleAction(
            action_type=ActionType.CLOSE_TRAILING_STOP,
            reason=(
                f"Trailing stop triggered (short): price {current_price:.6f} "
                f">= trailing_stop {new_trailing_stop:.6f} "
                f"(lowest_seen={new_lowest:.6f}, pct={pct}%)"
            ),
            close_price=current_price,
            new_trailing_stop=new_trailing_stop,
            new_lowest_seen=new_lowest,
            metadata={
                "trailing_stop_pct":   pct,
                "lowest_price_seen":   new_lowest,
                "trailing_stop_price": new_trailing_stop,
                "current_price":       current_price,
                "direction":           "short",
            },
        )

    price_moved = new_lowest < previous_lowest

    if price_moved or (trade.trailing_stop_price is None):
        return LifecycleAction(
            action_type=ActionType.UPDATE_TRAILING_STOP,
            reason=(
                f"Trailing stop updated (short): "
                f"lowest={new_lowest:.6f}, stop={new_trailing_stop:.6f}"
            ),
            new_trailing_stop=new_trailing_stop,
            new_lowest_seen=new_lowest,
            metadata={
                "trailing_stop_pct":   pct,
                "lowest_price_seen":   new_lowest,
                "trailing_stop_price": new_trailing_stop,
                "current_price":       current_price,
            },
        )

    return hold()
