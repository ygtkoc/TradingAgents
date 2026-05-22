"""
PnL-denominated lifecycle triggers.

These are a protective backstop for trades that carry risk_amount and
expected_reward in quote currency. Price-level SL/TP remains the primary
trigger, but a trade must also close once its live P&L crosses the stored
per-trade risk or reward budget.
"""
from __future__ import annotations

from src.db.models import Trade
from src.lifecycle.action import ActionType, LifecycleAction, hold


def check_pnl_stop_loss(
    trade: Trade,
    current_price: float,
    unrealized_pnl: float,
) -> LifecycleAction:
    """Close when unrealized loss reaches the stored per-trade risk amount."""
    risk_amount = _positive_float(trade.risk_amount)
    if risk_amount is None:
        return hold()

    loss_limit = -risk_amount
    if unrealized_pnl > loss_limit:
        return hold()

    return LifecycleAction(
        action_type=ActionType.CLOSE_STOP_LOSS,
        reason=(
            f"PnL stop-loss triggered: unrealized_pnl {unrealized_pnl:.2f} "
            f"<= loss_limit {loss_limit:.2f}"
        ),
        close_price=current_price,
        metadata={
            "trigger_rule": "unrealized_pnl <= -risk_amount",
            "current_price": current_price,
            "unrealized_pnl": unrealized_pnl,
            "risk_amount": risk_amount,
            "loss_limit": loss_limit,
            "direction": trade.direction,
            "protection_reason": (
                "Stored per-trade risk budget was reached; position closed "
                "to cap downside risk."
            ),
        },
    )


def check_pnl_take_profit(
    trade: Trade,
    current_price: float,
    unrealized_pnl: float,
) -> LifecycleAction:
    """Close when unrealized profit reaches the stored reward target."""
    reward_target = _reward_target(trade)
    if reward_target is None:
        return hold()

    if unrealized_pnl < reward_target:
        return hold()

    return LifecycleAction(
        action_type=ActionType.CLOSE_TAKE_PROFIT,
        reason=(
            f"PnL take-profit triggered: unrealized_pnl {unrealized_pnl:.2f} "
            f">= reward_target {reward_target:.2f}"
        ),
        close_price=current_price,
        metadata={
            "trigger_rule": "unrealized_pnl >= expected_reward",
            "current_price": current_price,
            "unrealized_pnl": unrealized_pnl,
            "expected_reward": reward_target,
            "risk_amount": trade.risk_amount,
            "risk_reward_ratio": trade.risk_reward_ratio,
            "direction": trade.direction,
        },
    )


def _reward_target(trade: Trade) -> float | None:
    expected_reward = _positive_float(trade.expected_reward)
    if expected_reward is not None:
        return expected_reward

    risk_amount = _positive_float(trade.risk_amount)
    risk_reward_ratio = _positive_float(trade.risk_reward_ratio)
    if risk_amount is None or risk_reward_ratio is None:
        return None
    return risk_amount * risk_reward_ratio


def _positive_float(value: float | None) -> float | None:
    try:
        parsed = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    if parsed is None or parsed <= 0:
        return None
    return parsed
