"""
Automatic reward/R and scaled take-profit plan generation.

The planner keeps bot-level fixed R/R as a fallback only. New decisions should
carry a reward_plan from the agent pipeline, but execution still normalizes the
plan defensively before persisting a trade.
"""
from __future__ import annotations

from typing import Any


def build_reward_plan(
    *,
    entry_price: float,
    stop_loss: float,
    direction: str,
    requested_reward_r: float | None = None,
    max_reward_r: float = 5.0,
    min_reward_r: float = 1.5,
    close_profile: str = "balanced",
) -> dict[str, Any]:
    """Return a normalized TP plan with three ordered levels."""
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
        "source": "auto_reward_planner",
        "selected_reward_r": round(selected_r, 6),
        "max_reward_r": round(max_r, 6),
        "min_reward_r": round(min_r, 6),
        "close_profile": close_profile,
        "levels": levels,
    }


def normalize_reward_plan(
    *,
    risk_summary: dict[str, Any],
    entry_price: float,
    stop_loss: float,
    direction: str,
    max_reward_r: float = 5.0,
    min_reward_r: float = 1.5,
) -> dict[str, Any]:
    """Normalize an agent-provided plan, or build a fallback plan."""
    raw_plan = risk_summary.get("reward_plan") or risk_summary.get("tp_plan")
    requested_r = _as_float(
        (raw_plan or {}).get("selected_reward_r") if isinstance(raw_plan, dict) else None
    )
    requested_r = requested_r or _as_float(risk_summary.get("risk_reward_ratio"))
    profile = (
        str((raw_plan or {}).get("close_profile"))
        if isinstance(raw_plan, dict) and (raw_plan or {}).get("close_profile")
        else str(risk_summary.get("tp_close_profile") or "balanced")
    )

    plan = build_reward_plan(
        entry_price=entry_price,
        stop_loss=stop_loss,
        direction=direction,
        requested_reward_r=requested_r,
        max_reward_r=max_reward_r,
        min_reward_r=min_reward_r,
        close_profile=profile,
    )
    if not plan:
        return {}

    if isinstance(raw_plan, dict):
        plan["source"] = raw_plan.get("source") or plan["source"]
        plan["planner_confidence"] = raw_plan.get("planner_confidence")
        plan["rationale"] = raw_plan.get("rationale")
    return plan


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


def _as_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))
