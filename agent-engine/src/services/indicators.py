"""
Technical indicator computation from OHLCV price series.
Uses pandas + numpy; pandas-ta for composite indicators.

All functions accept plain Python lists and return Optional[float] so
they are safe to call when data is sparse. They never raise — callers
must handle None returns gracefully.
"""
from __future__ import annotations

from typing import Optional
import numpy as np
import pandas as pd


# ── Core indicator functions ──────────────────────────────────────────────────

def compute_rsi(closes: list[float], period: int = 14) -> Optional[float]:
    """Wilder RSI. Returns None if insufficient data."""
    if len(closes) < period + 1:
        return None
    s = pd.Series(closes, dtype=float)
    delta = s.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / (loss + 1e-10)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return float(rsi.iloc[-1])


def compute_ema(closes: list[float], period: int = 20) -> Optional[float]:
    if len(closes) < period:
        return None
    s = pd.Series(closes, dtype=float)
    ema = s.ewm(span=period, adjust=False).mean()
    return float(ema.iloc[-1])


def compute_sma(closes: list[float], period: int = 20) -> Optional[float]:
    if len(closes) < period:
        return None
    return float(np.mean(closes[-period:]))


def compute_macd(
    closes: list[float],
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Returns (macd_line, signal_line, histogram). All None if insufficient data."""
    if len(closes) < slow + signal_period:
        return None, None, None
    s = pd.Series(closes, dtype=float)
    ema_fast = s.ewm(span=fast, adjust=False).mean()
    ema_slow = s.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal = macd_line.ewm(span=signal_period, adjust=False).mean()
    histogram = macd_line - signal
    return float(macd_line.iloc[-1]), float(signal.iloc[-1]), float(histogram.iloc[-1])


def compute_atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    df = pd.DataFrame({"high": highs, "low": lows, "close": closes})
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    return float(atr.iloc[-1])


def compute_bollinger_bands(
    closes: list[float], period: int = 20, std_dev: float = 2.0
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Returns (upper, middle, lower). All None if insufficient data."""
    if len(closes) < period:
        return None, None, None
    s = pd.Series(closes[-period:], dtype=float)
    middle = float(s.mean())
    std = float(s.std())
    return middle + std_dev * std, middle, middle - std_dev * std


def compute_volume_sma(volumes: list[float], period: int = 20) -> Optional[float]:
    return compute_sma(volumes, period)


def price_momentum(closes: list[float], lookback: int = 5) -> Optional[float]:
    """Simple price rate-of-change over lookback bars, as a percentage."""
    if len(closes) < lookback + 1:
        return None
    old = closes[-(lookback + 1)]
    current = closes[-1]
    if old == 0:
        return None
    return ((current - old) / old) * 100.0


def volume_momentum(volumes: list[float], lookback: int = 5) -> Optional[float]:
    """Volume relative to its SMA — > 1.0 means above-average volume."""
    if len(volumes) < max(lookback + 1, 20):
        return None
    avg_vol = compute_volume_sma(volumes[:-lookback], 20)
    if not avg_vol or avg_vol == 0:
        return None
    recent_avg = float(np.mean(volumes[-lookback:]))
    return recent_avg / avg_vol


def detect_trend(closes: list[float], short: int = 20, long: int = 50) -> Optional[str]:
    """
    Returns 'uptrend', 'downtrend', or 'sideways' based on EMA crossover.
    Returns None if insufficient data.
    """
    ema_short = compute_ema(closes, short)
    ema_long = compute_ema(closes, long)
    if ema_short is None or ema_long is None:
        return None
    diff_pct = (ema_short - ema_long) / ema_long * 100
    if diff_pct > 0.5:
        return "uptrend"
    if diff_pct < -0.5:
        return "downtrend"
    return "sideways"


def is_overbought(rsi: Optional[float], threshold: float = 70.0) -> bool:
    return rsi is not None and rsi >= threshold


def is_oversold(rsi: Optional[float], threshold: float = 30.0) -> bool:
    return rsi is not None and rsi <= threshold


def compute_vwap(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    volumes: list[float],
) -> Optional[float]:
    """Volume-Weighted Average Price over the supplied bars.

    Returns None when any input list is empty or all volumes are zero.
    """
    if not closes or not volumes or len(closes) != len(volumes):
        return None
    typical = [(h + l + c) / 3 for h, l, c in zip(highs, lows, closes)]
    tpv = sum(tp * v for tp, v in zip(typical, volumes))
    total_vol = sum(volumes)
    if total_vol == 0:
        return None
    return tpv / total_vol


def compute_stochastic(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    k_period: int = 14,
    d_period: int = 3,
) -> tuple[Optional[float], Optional[float]]:
    """Stochastic oscillator (%K, %D). Returns (None, None) if insufficient data."""
    if len(closes) < k_period:
        return None, None
    recent_high = max(highs[-k_period:])
    recent_low  = min(lows[-k_period:])
    if recent_high == recent_low:
        return None, None
    k = (closes[-1] - recent_low) / (recent_high - recent_low) * 100
    # %D: simple average of last d_period %K values (simplified one-value output)
    return float(k), float(k)   # full D-smoothing needs series; keep it simple


def compute_cci(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 20,
) -> Optional[float]:
    """Commodity Channel Index. Returns None if insufficient data."""
    if len(closes) < period:
        return None
    typical = [(h + l + c) / 3 for h, l, c in zip(highs[-period:], lows[-period:], closes[-period:])]
    tp_mean = float(np.mean(typical))
    mean_dev = float(np.mean([abs(tp - tp_mean) for tp in typical]))
    if mean_dev == 0:
        return None
    return (typical[-1] - tp_mean) / (0.015 * mean_dev)


def detect_volume_spike(
    volumes: list[float],
    lookback: int = 20,
    spike_threshold: float = 2.5,
) -> bool:
    """Returns True when the most recent bar's volume is spike_threshold× the SMA."""
    if len(volumes) < lookback + 1:
        return False
    avg = float(np.mean(volumes[-lookback - 1:-1]))
    if avg <= 0:
        return False
    return volumes[-1] >= avg * spike_threshold


def detect_support_resistance(
    closes: list[float],
    lows: list[float],
    highs: list[float],
    lookback: int = 20,
) -> dict:
    """Simple swing high/low pivot-based support/resistance.

    Returns {
        'support': float,      # nearest swing low below current price
        'resistance': float,   # nearest swing high above current price
        'at_support': bool,    # price within 0.5% of support
        'at_resistance': bool, # price within 0.5% of resistance
    }
    """
    if len(closes) < 5:
        return {}

    current = closes[-1]
    window_highs = highs[-lookback:]
    window_lows  = lows[-lookback:]

    # Simple: use 20-bar high/low as resistance/support
    resistance = max(window_highs)
    support    = min(window_lows)

    at_support    = current <= support    * 1.005
    at_resistance = current >= resistance * 0.995

    return {
        "support":        support,
        "resistance":     resistance,
        "at_support":     at_support,
        "at_resistance":  at_resistance,
        "sr_range_pct":   (resistance - support) / support * 100 if support > 0 else 0.0,
    }


def detect_higher_highs_lower_lows(
    highs: list[float],
    lows: list[float],
    lookback: int = 5,
) -> dict:
    """Detects higher-high / lower-low market structure over `lookback` bars."""
    if len(highs) < lookback * 2:
        return {"structure": "insufficient_data"}

    recent_highs  = highs[-lookback:]
    prior_highs   = highs[-lookback * 2:-lookback]
    recent_lows   = lows[-lookback:]
    prior_lows    = lows[-lookback * 2:-lookback]

    hh = max(recent_highs) > max(prior_highs)
    ll = min(recent_lows)  < min(prior_lows)
    hl = min(recent_lows)  > min(prior_lows)
    lh = max(recent_highs) < max(prior_highs)

    if hh and hl:
        structure = "bullish"      # HH + HL
    elif ll and lh:
        structure = "bearish"      # LL + LH
    elif hh and ll:
        structure = "expansion"    # range widening
    else:
        structure = "consolidation"

    return {
        "structure":     structure,
        "higher_high":   hh,
        "lower_low":     ll,
        "higher_low":    hl,
        "lower_high":    lh,
    }
