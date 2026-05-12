"""
In-memory cache of the latest kline per symbol.

Single asyncio loop → no lock required. Reads are fast and lock-free.
"""
from __future__ import annotations

import time
from typing import Optional

from src.services.market_data.models import Kline


class MarketDataCache:
    """Latest observed kline per internal symbol (e.g. `BTC/USDT`)."""

    def __init__(self) -> None:
        self._latest:        dict[str, Kline] = {}
        self._last_update_m: dict[str, float] = {}
        self._global_last_update_m: float = 0.0

    def update(self, kline: Kline) -> None:
        self._latest[kline.symbol_internal]        = kline
        self._last_update_m[kline.symbol_internal] = time.monotonic()
        self._global_last_update_m                 = time.monotonic()

    def latest(self, symbol_internal: str) -> Optional[Kline]:
        return self._latest.get(symbol_internal)

    def all(self) -> dict[str, Kline]:
        return dict(self._latest)

    def age_seconds(self, symbol_internal: str) -> Optional[float]:
        m = self._last_update_m.get(symbol_internal)
        return None if m is None else time.monotonic() - m

    def global_age_seconds(self) -> Optional[float]:
        if self._global_last_update_m == 0.0:
            return None
        return time.monotonic() - self._global_last_update_m
