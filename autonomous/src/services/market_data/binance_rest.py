"""
Binance public REST client — fallback when the WebSocket is unhealthy.

Pulls the latest closed kline per symbol via /api/v3/klines. Public data,
no auth. The Feed alternates between WS and REST: when the WS hasn't
yielded anything for `market_data_rest_fallback_seconds`, the Feed runs a
single REST poll cycle to keep snapshots flowing.

`fetch_kline_history` fetches a batch of *closed* historical klines for
pre-seeding market_snapshots at service startup. This gives the agent-engine
risk assessors enough bars (≥ 50) to compute ATR/RSI immediately rather than
waiting 50+ minutes for real-time candles to accumulate.
"""
from __future__ import annotations

import httpx

from src.config import settings
from src.logging_config import get_logger
from src.services.market_data.models import Kline, to_internal

log = get_logger(__name__)


async def fetch_spot_usdt_symbols() -> list[str]:
    """Return every currently-trading Binance spot USDT pair in compact form."""
    url = f"{settings.market_data_binance_rest_url}/api/v3/exchangeInfo"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(url)
            r.raise_for_status()
            payload = r.json()
    except Exception as exc:
        log.warning("binance_rest.exchange_info_failed", error=str(exc)[:200])
        return []

    rows = payload.get("symbols") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []

    symbols: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").upper()
        if (
            row.get("status") == "TRADING"
            and row.get("quoteAsset") == "USDT"
            and bool(row.get("isSpotTradingAllowed", True))
            and symbol.endswith("USDT")
            and not any(token in symbol for token in ("UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT"))
        ):
            symbols.append(symbol)

    return sorted(set(symbols))


async def fetch_latest_kline(symbol_binance: str, interval: str) -> Kline | None:
    """Fetch the most recent kline (open candle) — sufficient for keeping a
    snapshot pipeline warm during a WS outage."""
    url    = f"{settings.market_data_binance_rest_url}/api/v3/klines"
    params = {"symbol": symbol_binance, "interval": interval, "limit": 1}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            rows = r.json()
    except Exception as exc:
        log.warning("binance_rest.fetch_failed", symbol=symbol_binance, error=str(exc)[:200])
        return None

    if not rows or not isinstance(rows, list):
        return None
    row = rows[0]

    internal = to_internal(symbol_binance)
    if internal is None:
        return None

    try:
        return Kline(
            symbol_internal=internal,
            symbol_binance=symbol_binance,
            interval=interval,
            open_time_ms=int(row[0]),
            close_time_ms=int(row[6]),
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
            # REST returns the open candle; we treat it as "live" (not closed).
            is_closed=False,
            source="rest",
        )
    except (TypeError, ValueError, IndexError) as exc:
        log.warning("binance_rest.parse_failed", symbol=symbol_binance, error=str(exc)[:200])
        return None


async def fetch_kline_history(
    symbol_binance: str,
    interval: str,
    limit: int = 200,
) -> list[Kline]:
    """Fetch up to `limit` historical *closed* klines from Binance REST.

    Used at service startup to pre-seed market_snapshots so the risk agent
    has enough bars (≥ 50) for ATR/RSI calculations immediately, rather than
    waiting 50+ minutes for real-time klines to accumulate.

    The final kline in the Binance response is the currently-open candle and
    is excluded — all returned Klines have `is_closed=True`.
    """
    url    = f"{settings.market_data_binance_rest_url}/api/v3/klines"
    params = {"symbol": symbol_binance, "interval": interval, "limit": limit}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            rows = r.json()
    except Exception as exc:
        log.warning(
            "binance_rest.history_fetch_failed",
            symbol=symbol_binance,
            error=str(exc)[:200],
        )
        return []

    if not rows or not isinstance(rows, list):
        return []

    internal = to_internal(symbol_binance)
    if internal is None:
        return []

    klines: list[Kline] = []
    # Exclude the last row — it is the currently-open candle.
    for row in rows[:-1]:
        try:
            klines.append(Kline(
                symbol_internal=internal,
                symbol_binance=symbol_binance,
                interval=interval,
                open_time_ms=int(row[0]),
                close_time_ms=int(row[6]),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
                is_closed=True,
                source="rest_backfill",
            ))
        except (TypeError, ValueError, IndexError) as exc:
            log.debug(
                "binance_rest.history_parse_skip",
                symbol=symbol_binance,
                error=str(exc)[:100],
            )
            continue

    log.info(
        "binance_rest.history_fetched",
        symbol=symbol_binance,
        interval=interval,
        bars=len(klines),
    )
    return klines
