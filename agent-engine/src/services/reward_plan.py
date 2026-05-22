"""Reward/R planning helpers for agent-side decision enrichment."""
from __future__ import annotations

from typing import Any


def build_reward_plan(
    *,
    entry_price: float,
    stop_loss: float,
    direction: str,
    requested_reward_r: float | None,
    max_reward_r: float,
    min_reward_r: float = 1.5,
    close_profile: str = "balanced",
    source: str = "reward_plan_agent",
    rationale: str | None = None,
    confidence: float | None = None,
) -> dict[str, Any]:
    stop_distance = abs(float(entry_price) - float(stop_loss))
    if entry_price <= 0 or stop_loss <= 0 or stop_distance <= 0:
        return {}

    max_r = _clamp(max_reward_r, 1.0, 10.0)
    min_r = _clamp(min_reward_r, 0.5, max_r)
    selected_r = _clamp(requested_reward_r or min(2.0, max_r), min_r, max_r)
    r_levels = _r_levels(selected_r)
    close_pcts = _close_pcts(close_profile, selected_r)
    levels = []
    for idx, (r_value, close_pct) in enumerate(zip(r_levels, close_pcts), start=1):
        price = (
            entry_price - stop_distance * r_value
            if direction == "short"
            else entry_price + stop_distance * r_value
        )
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
        "source": source,
        "selected_reward_r": round(selected_r, 6),
        "max_reward_r": round(max_r, 6),
        "min_reward_r": round(min_r, 6),
        "close_profile": close_profile,
        "planner_confidence": confidence,
        "rationale": rationale,
        "levels": levels,
    }


def final_take_profit(plan: dict[str, Any]) -> float | None:
    levels = plan.get("levels") if isinstance(plan, dict) else None
    if not levels:
        return None
    try:
        return float(levels[-1]["price"])
    except (KeyError, TypeError, ValueError):
        return None


def _r_levels(selected_r: float) -> list[float]:
    if selected_r <= 1.5:
        return [selected_r * 0.5, selected_r * 0.8, selected_r]
    return [min(1.0, selected_r * 0.5), max(1.1, selected_r * 0.65), selected_r]


def _close_pcts(profile: str, selected_r: float) -> list[float]:
    if profile == "conservative" or selected_r <= 2.0:
        return [0.40, 0.35, 0.25]
    if profile == "runner":
        return [0.25, 0.30, 0.45]
    return [0.30, 0.40, 0.30]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))
