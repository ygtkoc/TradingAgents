"""
MarketDataService — fetches current price and market snapshot.

Reads from market_snapshots table (populated by a separate data feed service).
Falls back to None when no snapshot is available — callers must handle this
case (risk guard will block live trades with no price data).
"""
from __future__ import annotations

from typing import Optional

from src.db.models import MarketSnapshot
from src.db.repositories import MarketDataRepository
from src.logging_config import get_logger

log = get_logger(__name__)


class MarketDataService:

    def __init__(self) -> None:
        self._repo = MarketDataRepository()

    async def get_snapshot(
        self,
        exchange: str,
        symbol: str,
        timeframe: str = "1h",
    ) -> Optional[MarketSnapshot]:
        """
        Fetch the latest market snapshot for a symbol.

        Returns None if no snapshot is available.
        Callers should treat None as "price unknown" and block live execution.
        """
        timeframes = [timeframe]
        if timeframe == "1h":
            timeframes.append("1m")

        for current_timeframe in timeframes:
            snapshot = await self._repo.get_latest(exchange, symbol, current_timeframe)
            if snapshot is None:
                continue

            if current_timeframe != timeframe:
                log.info(
                    "market_data.timeframe_fallback",
                    exchange=exchange,
                    symbol=symbol,
                    requested_timeframe=timeframe,
                    fallback_timeframe=current_timeframe,
                )

            log.debug(
                "market_data.snapshot_fetched",
                exchange=exchange,
                symbol=symbol,
                timeframe=current_timeframe,
                price=snapshot.close_price,
                captured_at=snapshot.captured_at,
            )
            return snapshot

        log.warning(
            "market_data.no_snapshot",
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
        )
        return None

    async def get_current_price(
        self,
        exchange: str,
        symbol: str,
    ) -> Optional[float]:
        """
        Return just the latest close price, or None if unavailable.
        """
        snapshot = await self.get_snapshot(exchange, symbol)
        return snapshot.close_price if snapshot else None
