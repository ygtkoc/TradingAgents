"""Scaled TP1/TP2/TP3 trigger checks."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.db.models import Trade
from src.lifecycle.action import ActionType, LifecycleAction, hold


def check_scaled_take_profit(trade: Trade, current_price: float) -> LifecycleAction:
    """Return a partial/full take-profit action for the next pending TP level."""
    plan = _plan(trade)
    levels = plan.get("levels") if isinstance(plan, dict) else None
    if not levels:
        return hold()

    for level in sorted(levels, key=lambda item: int(item.get("level", 0))):
        if str(level.get("status") or "pending") != "pending":
            continue
        price = _float(level.get("price"))
        if price is None:
            continue
        hit = current_price >= price if trade.is_long else current_price <= price
        if not hit:
            return hold()

        level_no = int(level.get("level") or 1)
        is_final = level_no >= max(int(item.get("level", 0) or 0) for item in levels)
        close_pct = 1.0 if is_final else _close_pct(level)
        close_qty = trade.effective_quantity if is_final else trade.effective_quantity * close_pct
        comparator = ">=" if trade.is_long else "<="

        return LifecycleAction(
            action_type=ActionType.CLOSE_TAKE_PROFIT,
            reason=(
                f"Scaled take-profit {level.get('label') or level_no} triggered: "
                f"price {current_price} {comparator} target {price}"
            ),
            close_price=current_price,
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


def _plan(trade: Trade) -> dict[str, Any]:
    raw = trade.metadata.get("reward_plan") or {}
    if isinstance(raw, dict) and raw.get("levels"):
        return raw
    levels = trade.metadata.get("tp_plan")
    if isinstance(levels, list) and levels:
        return {"mode": "scaled_take_profit", "levels": levels}
    return {}


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
