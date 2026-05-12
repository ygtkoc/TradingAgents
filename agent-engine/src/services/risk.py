"""
Risk calculation helpers for the risk agent layer.

These are pure functions that operate on price data and bot configs —
they do NOT read from the database.
"""
from __future__ import annotations

from typing import Optional


def calculate_position_size(
    account_balance: float,
    risk_per_trade_pct: float,
    entry_price: float,
    stop_loss_price: float,
) -> Optional[float]:
    """
    Kelly-lite position sizing based on risk per trade.

    Returns the position size in base currency units, or None if
    the calculation is invalid (zero stop distance, etc.).

    Args:
        account_balance:    Total account balance in quote currency.
        risk_per_trade_pct: Max percentage of balance to risk (e.g. 1.0 = 1%).
        entry_price:        Intended entry price.
        stop_loss_price:    Intended stop-loss price.
    """
    if entry_price <= 0 or stop_loss_price <= 0:
        return None
    stop_distance = abs(entry_price - stop_loss_price)
    if stop_distance <= 0:
        return None
    risk_amount = account_balance * (risk_per_trade_pct / 100.0)
    size = risk_amount / stop_distance
    return size


def calculate_risk_reward_ratio(
    entry_price: float,
    stop_loss_price: float,
    take_profit_price: float,
) -> Optional[float]:
    """
    Returns the R:R ratio (reward / risk).
    Returns None if prices are invalid or stop distance is zero.
    """
    risk = abs(entry_price - stop_loss_price)
    reward = abs(take_profit_price - entry_price)
    if risk <= 0:
        return None
    return reward / risk


def assess_volatility_regime(atr_pct: float) -> str:
    """
    Classifies market volatility based on ATR as % of price.

    Returns: 'low' | 'normal' | 'elevated' | 'high' | 'extreme'
    """
    if atr_pct < 0.5:
        return "low"
    if atr_pct < 1.5:
        return "normal"
    if atr_pct < 3.0:
        return "elevated"
    if atr_pct < 5.0:
        return "high"
    return "extreme"


def max_drawdown(equity_curve: list[float]) -> Optional[float]:
    """
    Computes the maximum drawdown percentage from an equity curve.
    Returns None for curves with fewer than 2 points.
    """
    if len(equity_curve) < 2:
        return None
    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        if value > peak:
            peak = value
        drawdown = (peak - value) / peak if peak > 0 else 0.0
        if drawdown > max_dd:
            max_dd = drawdown
    return max_dd * 100.0  # Return as percentage
