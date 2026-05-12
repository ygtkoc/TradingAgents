"""
Market-data domain types and symbol mapping.

Binance uses the compact symbol form `BTCUSDT`. The rest of the platform
(bots.trading_pairs, market_snapshots.symbol, signals.symbol) uses the
slash form `BTC/USDT`. This module owns the mapping in both directions.

Symbol resolution is dynamic: any `BASE/USDT` pair is accepted, not just
the three bootstrapped ones. Static INTERNAL_TO_BINANCE is the seed; dynamic
conversions handle user-created bot symbols (DOGE/USDT, ARB/USDT, etc.).
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


# ── Static seed mapping (well-known pairs) ───────────────────────────────────

INTERNAL_TO_BINANCE: dict[str, str] = {
    "BTC/USDT": "BTCUSDT",
    "ETH/USDT": "ETHUSDT",
    "SOL/USDT": "SOLUSDT",
}

BINANCE_TO_INTERNAL: dict[str, str] = {v: k for k, v in INTERNAL_TO_BINANCE.items()}


def to_internal(symbol: str) -> Optional[str]:
    """`BTCUSDT` → `BTC/USDT`.

    Handles any `BASEUSDT` pair dynamically — not just the static seed.
    Returns None for non-USDT or malformed symbols.
    """
    if not symbol:
        return None

    if "/" in symbol:
        # Already slash-form — normalise case and validate it's a USDT pair.
        up = symbol.upper()
        if up.endswith("/USDT") and len(up) > 5:
            return up   # e.g. "btc/usdt" → "BTC/USDT"
        return None

    upper = symbol.upper()

    # Fast path: static lookup.
    if upper in BINANCE_TO_INTERNAL:
        return BINANCE_TO_INTERNAL[upper]

    # Dynamic: any XYZUSDT → XYZ/USDT (Binance USDT spot pairs).
    if upper.endswith("USDT") and len(upper) > 4:
        base = upper[:-4]
        if base:
            return f"{base}/USDT"

    return None


def to_binance(symbol: str) -> Optional[str]:
    """`BTC/USDT` → `BTCUSDT`.

    Handles any `BASE/USDT` pair dynamically — not just the static seed.
    Returns None for non-USDT or malformed symbols.
    """
    if not symbol:
        return None

    if "/" not in symbol:
        upper = symbol.upper()
        # Accept bare Binance symbols (no slash) only if USDT-quoted.
        if upper.endswith("USDT") and len(upper) > 4:
            return upper
        return None

    # Fast path: static lookup.
    if symbol in INTERNAL_TO_BINANCE:
        return INTERNAL_TO_BINANCE[symbol]

    # Dynamic: BTC/USDT → BTCUSDT.
    parts = symbol.upper().split("/")
    if len(parts) == 2 and parts[1] == "USDT" and parts[0]:
        return f"{parts[0]}USDT"

    return None


# ── Kline (candle) ───────────────────────────────────────────────────────────

class Kline(BaseModel):
    """One candle observation. Source can be either WebSocket or REST."""

    symbol_internal: str            # "BTC/USDT"
    symbol_binance:  str            # "BTCUSDT"
    interval:        str            # "1m"
    open_time_ms:    int
    close_time_ms:   int
    open:            float
    high:            float
    low:             float
    close:           float
    volume:          float
    is_closed:       bool           # True only when the candle is final
    source:          str            # "ws" | "rest"
