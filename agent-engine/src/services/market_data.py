"""
Market data service — fetches snapshots from Supabase market_snapshots table.

TODO(exchange-adapters): When live exchange adapters are built, this service
  will first try the exchange WebSocket/REST for a fresh snapshot, then fall
  back to the DB cache. For now, the DB is the only source.
"""
from __future__ import annotations

from typing import Optional

from src.db.models import MarketSnapshot
from src.db.repositories import MarketDataRepository
from src.logging_config import get_logger
from src.utils.time import is_stale
from src.config import settings

log = get_logger(__name__)

_market_repo = MarketDataRepository()


async def get_latest_snapshot(
    exchange: str,
    symbol: str,
    timeframe: str = "1h",
) -> Optional[MarketSnapshot]:
    """
    Fetches the most recent market snapshot from the DB.
    Returns None if no snapshot exists.
    Logs a warning if the snapshot is stale but still returns it
    (the DataQualityAgent will apply the staleness penalty).
    """
    snapshot = await _market_repo.get_latest(exchange, symbol, timeframe)
    resolved_timeframe = timeframe

    if snapshot is None and timeframe != "1m":
        fallback = await _market_repo.get_latest(exchange, symbol, "1m")
        if fallback is not None:
            snapshot = fallback
            resolved_timeframe = "1m"
            log.info(
                "market_data.timeframe_fallback",
                exchange=exchange,
                symbol=symbol,
                requested_timeframe=timeframe,
                resolved_timeframe=resolved_timeframe,
            )

    if snapshot is None:
        log.warning(
            "market_data.no_snapshot",
            exchange=exchange,
            symbol=symbol,
            timeframe=resolved_timeframe,
        )
        return None

    if is_stale(snapshot.captured_at, settings.max_stale_snapshot_minutes):
        log.warning(
            "market_data.stale_snapshot",
            exchange=exchange,
            symbol=symbol,
            captured_at=snapshot.captured_at,
            max_age_minutes=settings.max_stale_snapshot_minutes,
        )

    return snapshot


async def get_price_history(
    exchange: str,
    symbol: str,
    timeframe: str = "1h",
    limit: int = 50,
) -> list[MarketSnapshot]:
    """Returns up to `limit` snapshots in descending order (newest first)."""
    history = await _market_repo.get_history(exchange, symbol, timeframe, limit)
    if history or timeframe == "1m":
        return history

    fallback_history = await _market_repo.get_history(exchange, symbol, "1m", limit)
    if fallback_history:
        log.info(
            "market_data.history_timeframe_fallback",
            exchange=exchange,
            symbol=symbol,
            requested_timeframe=timeframe,
            resolved_timeframe="1m",
            bars=len(fallback_history),
        )
    return fallback_history


def extract_closes(snapshots: list[MarketSnapshot]) -> list[float]:
    """Extracts close prices in chronological order (oldest first)."""
    return [s.close_price for s in reversed(snapshots)]


def extract_volumes(snapshots: list[MarketSnapshot]) -> list[float]:
    return [s.volume for s in reversed(snapshots)]


def extract_highs(snapshots: list[MarketSnapshot]) -> list[float]:
    return [s.high_price for s in reversed(snapshots)]


def extract_lows(snapshots: list[MarketSnapshot]) -> list[float]:
    return [s.low_price for s in reversed(snapshots)]


def calculate_spread_pct(snapshot: MarketSnapshot) -> Optional[float]:
    """
    Calculates spread as a percentage of the mid price.
    Uses stored spread_pct if available, otherwise derives from bid/ask.
    """
    if snapshot.spread_pct is not None:
        return snapshot.spread_pct
    if snapshot.bid_price and snapshot.ask_price:
        mid = (snapshot.bid_price + snapshot.ask_price) / 2
        if mid > 0:
            return abs(snapshot.ask_price - snapshot.bid_price) / mid * 100
    return None
