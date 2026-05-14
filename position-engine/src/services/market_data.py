"""MarketDataService — current price and snapshot from DB."""
from __future__ import annotations

from typing import Optional

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
        if snap is None:
            log.warning("market_data.no_snapshot", exchange=exchange, symbol=symbol, timeframe=timeframe)
        return snap

    async def get_current_price(self, exchange: str, symbol: str) -> Optional[float]:
        snap = await self.get_snapshot(exchange, symbol)
        return snap.close_price if snap else None
