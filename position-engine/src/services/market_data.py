"""MarketDataService — current price and snapshot from DB."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

import httpx

from src.config import settings
from src.db.models import MarketSnapshot
from src.db.repositories import MarketDataRepository
from src.logging_config import get_logger

log = get_logger(__name__)


class MarketDataService:
    def __init__(self) -> None:
        self._repo = MarketDataRepository()

    async def get_snapshot(
        self, exchange: str, symbol: str, timeframe: str | None = None
    ) -> Optional[MarketSnapshot]:
        timeframe = timeframe or settings.market_data_kline_interval
        snap = await self._repo.get_latest(exchange, symbol, timeframe)
        live_price = await self._get_live_price(exchange, symbol)
        if live_price is not None:
            if snap is not None:
                return snap.model_copy(update={"close_price": live_price})
            return MarketSnapshot(
                id=f"live:{exchange}:{symbol}",
                exchange=exchange,
                symbol=symbol,
                timeframe=timeframe,
                open_price=live_price,
                high_price=live_price,
                low_price=live_price,
                close_price=live_price,
                volume=0.0,
                spread_pct=None,
                captured_at=datetime.now(UTC).isoformat(),
            )
        if snap is None:
            log.warning("market_data.no_snapshot", exchange=exchange, symbol=symbol, timeframe=timeframe)
        return snap

    async def get_current_price(self, exchange: str, symbol: str) -> Optional[float]:
        snap = await self.get_snapshot(exchange, symbol)
        return snap.close_price if snap else None

    async def _get_live_price(self, exchange: str, symbol: str) -> Optional[float]:
        if exchange.lower() != "binance":
            return None
        normalized = symbol.replace("/", "").upper()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    "https://api.binance.com/api/v3/ticker/price",
                    params={"symbol": normalized},
                )
                response.raise_for_status()
            price = float(response.json()["price"])
            return price if price > 0 else None
        except Exception as exc:
            log.warning(
                "market_data.live_price_failed",
                exchange=exchange,
                symbol=symbol,
                error=str(exc)[:200],
            )
            return None
