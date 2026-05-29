"""Scaled TP1/TP2/TP3 trigger checks."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.db.models import Trade
from src.lifecycle.action import ActionType, LifecycleAction, hold


def check_scaled_take_profit(
    trade: Trade,
    current_price: float,
    *,
    high_price: float | None = None,
    low_price: float | None = None,
) -> LifecycleAction:
    """Return a partial/full take-profit action for the next pending TP level."""
    plan = _plan(trade)
    levels = plan.get("levels") if isinstance(plan, dict) else None
    if not levels:
        return hold()
    high = high_price if high_price and high_price > 0 else current_price
    low = low_price if low_price and low_price > 0 else current_price

    for level in sorted(levels, key=lambda item: int(item.get("level", 0))):
        if str(level.get("status") or "pending") != "pending":
            continue
        price = _float(level.get("price"))
        if price is None:
            continue
        current_hit = current_price >= price if trade.is_long else current_price <= price
        range_hit = high >= price if trade.is_long else low <= price
        hit = current_hit or range_hit
        if not hit:
            return hold()

        level_no = int(level.get("level") or 1)
        is_final = level_no >= max(int(item.get("level", 0) or 0) for item in levels)
        close_pct = 1.0 if is_final else _close_pct(level)
        close_qty = trade.effective_quantity if is_final else trade.effective_quantity * close_pct
        comparator = ">=" if trade.is_long else "<="
        trigger_source = "current_price" if current_hit else "candle_range"
        trigger_price = current_price if current_hit else price
        trigger_observed_price = current_price if current_hit else (high if trade.is_long else low)

        return LifecycleAction(
            action_type=ActionType.CLOSE_TAKE_PROFIT,
            reason=(
                f"Scaled take-profit {level.get('label') or level_no} triggered: "
                f"price {trigger_observed_price} {comparator} target {price}"
            ),
            close_price=trigger_price,
            metadata={
                "scaled_take_profit": True,
                "tp_level": level_no,
                "tp_label": level.get("label") or f"TP{level_no}",
                "tp_price": price,
                "tp_r": _float(level.get("r")),
                "close_pct": close_pct,
                "close_quantity": close_qty,
                "is_final_tp": is_final,
                "current_price": current_price,
                "trigger_price": trigger_price,
                "trigger_observed_price": trigger_observed_price,
                "trigger_source": trigger_source,
                "high_price": high,
                "low_price": low,
                "direction": trade.direction,
                "reward_plan": plan,
            },
        )

    return hold()


def mark_level_hit(plan: dict[str, Any], level_no: int, *, qty: float, pnl: float, hit_at: str) -> dict[str, Any]:
    updated = deepcopy(plan)
    for level in updated.get("levels", []):
        if int(level.get("level", 0) or 0) == int(level_no):
            level["status"] = "hit"
            level["hit_at"] = hit_at
            level["filled_quantity"] = float(qty)
            level["realized_pnl"] = float(pnl)
            break
    return updated


def next_stop_after_tp(trade: Trade, plan: dict[str, Any], level_no: int) -> float | None:
    entry = trade.effective_entry_price
    if entry <= 0:
        return None
    if level_no <= 1:
        return entry
    levels = plan.get("levels", [])
    previous = None
    for level in levels:
        if int(level.get("level", 0) or 0) == level_no - 1:
            previous = _float(level.get("price"))
            break
    if previous is None:
        return entry
    return min(previous, trade.stop_loss or previous) if not trade.is_long else max(previous, trade.stop_loss or previous)


def next_take_profit_after_tp(plan: dict[str, Any], level_no: int) -> float | None:
    """Return the next pending TP price after a level is filled."""
    levels = plan.get("levels", []) if isinstance(plan, dict) else []
    for level in sorted(levels, key=lambda item: int(item.get("level", 0) or 0)):
        if int(level.get("level", 0) or 0) <= int(level_no):
            continue
        if str(level.get("status") or "pending") != "pending":
            continue
        return _float(level.get("price"))
    return None


def _plan(trade: Trade) -> dict[str, Any]:
    raw = trade.metadata.get("reward_plan") or {}
    if isinstance(raw, dict) and raw.get("levels"):
        return raw
    levels = trade.metadata.get("tp_plan")
    if isinstance(levels, list) and levels:
        return {"mode": "scaled_take_profit", "levels": levels}
    return _fallback_plan(trade)


def _fallback_plan(trade: Trade) -> dict[str, Any]:
    """Build a scaled TP plan for older trades that only stored final TP/R."""
    entry = trade.effective_entry_price
    stop = _float(trade.stop_loss)
    if entry <= 0 or stop is None or stop <= 0:
        return {}

    stop_distance = abs(entry - stop)
    if stop_distance <= 0:
        return {}

    selected_r = _float(trade.risk_reward_ratio)
    if selected_r is None and trade.take_profit:
        selected_r = abs(float(trade.take_profit) - entry) / stop_distance
    if selected_r is None or selected_r <= 0:
        return {}

    r_levels = _r_levels(selected_r)
    close_pcts = _close_pcts(selected_r)
    levels = []
    for idx, (r_value, close_pct) in enumerate(zip(r_levels, close_pcts), start=1):
        price = entry - stop_distance * r_value if not trade.is_long else entry + stop_distance * r_value
        levels.append({
            "level": idx,
            "label": f"TP{idx}",
            "r": round(r_value, 6),
            "price": round(price, 8),
            "close_pct": close_pct,
            "status": "pending",
            "hit_at": None,
            "filled_quantity": 0.0,
            "realized_pnl": 0.0,
        })

    return {
        "mode": "scaled_take_profit",
        "source": "position_engine_fallback",
        "selected_reward_r": round(selected_r, 6),
        "levels": levels,
    }


def _r_levels(selected_r: float) -> list[float]:
    if selected_r <= 1.5:
        return [selected_r * 0.5, selected_r * 0.8, selected_r]
    return [min(1.0, selected_r * 0.5), max(1.1, selected_r * 0.65), selected_r]


def _close_pcts(selected_r: float) -> list[float]:
    if selected_r <= 2.0:
        return [0.40, 0.35, 0.25]
    return [0.30, 0.40, 0.30]


def _close_pct(level: dict[str, Any]) -> float:
    value = _float(level.get("close_pct"))
    if value is None:
        return 0.0
    if value > 1:
        value = value / 100.0
    return max(0.0, min(1.0, value))


def _float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed
