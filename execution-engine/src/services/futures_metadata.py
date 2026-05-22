"""
Futures symbol metadata used by paper sizing.

Binance exposes the initial margin requirement in the public USD-M futures
exchangeInfo payload. For paper trading we derive the highest usable leverage
as 100 / requiredMarginPercent and fall back to a conservative configured
default when the public endpoint is unavailable.
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from src.config import settings
from src.logging_config import get_logger

log = get_logger(__name__)


class FuturesMetadataService:
    _TTL_SECONDS = 900.0

    def __init__(self) -> None:
        self._loaded_at = 0.0
        self._by_symbol: dict[str, dict[str, Any]] = {}

    async def max_leverage(self, exchange: str, symbol: str) -> float:
        if exchange.lower() != "binance":
            return settings.paper_default_max_leverage

        normalized = self._normalize_symbol(symbol)
        await self._ensure_loaded()
        row = self._by_symbol.get(normalized)
        if not row:
            return settings.paper_default_max_leverage

        try:
            required_margin_pct = float(row.get("requiredMarginPercent") or 0.0)
        except (TypeError, ValueError):
            required_margin_pct = 0.0

        if required_margin_pct <= 0:
            return settings.paper_default_max_leverage

        leverage = 100.0 / required_margin_pct
        return self._clamp_leverage(leverage)

    async def _ensure_loaded(self) -> None:
        now = time.monotonic()
        if self._by_symbol and (now - self._loaded_at) < self._TTL_SECONDS:
            return

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(settings.binance_futures_exchange_info_url)
                response.raise_for_status()
                payload = response.json()
            symbols = payload.get("symbols") or []
            self._by_symbol = {
                str(row.get("symbol") or "").upper(): row
                for row in symbols
                if row.get("symbol")
            }
            self._loaded_at = now
            log.info("futures_metadata.loaded", count=len(self._by_symbol))
        except Exception as exc:
            log.warning(
                "futures_metadata.load_failed",
                error=str(exc)[:200],
                fallback_leverage=settings.paper_default_max_leverage,
            )

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        return symbol.replace("/", "").replace("-", "").upper()

    @staticmethod
    def _clamp_leverage(leverage: float) -> float:
        return max(1.0, min(float(leverage), settings.paper_max_leverage_cap))
