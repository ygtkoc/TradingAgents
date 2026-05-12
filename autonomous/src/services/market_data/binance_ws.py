"""
Binance public combined-streams WebSocket client.

Subscribes to `<symbol>@kline_<interval>` for every requested symbol and
yields `Kline` objects as messages arrive. Reconnects with exponential
backoff on network failure. Public market data → no API key required.

Reference: https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

import websockets
from websockets.exceptions import ConnectionClosed

from src.config import settings
from src.logging_config import get_logger
from src.services.market_data.models import Kline, to_internal

log = get_logger(__name__)


def _parse_kline_msg(msg: dict) -> Kline | None:
    """Accept either a raw kline event or a combined-stream wrapper."""
    payload = msg.get("data", msg)            # combined-stream nests under .data
    if payload.get("e") != "kline":
        return None
    k = payload.get("k") or {}
    binance_symbol = (k.get("s") or payload.get("s") or "").upper()
    internal       = to_internal(binance_symbol)
    if internal is None:
        return None
    try:
        return Kline(
            symbol_internal=internal,
            symbol_binance=binance_symbol,
            interval=k.get("i", settings.market_data_kline_interval),
            open_time_ms=int(k.get("t", 0)),
            close_time_ms=int(k.get("T", 0)),
            open=float(k.get("o", 0.0)),
            high=float(k.get("h", 0.0)),
            low=float(k.get("l", 0.0)),
            close=float(k.get("c", 0.0)),
            volume=float(k.get("v", 0.0)),
            is_closed=bool(k.get("x", False)),
            source="ws",
        )
    except (TypeError, ValueError) as exc:
        log.warning("binance_ws.parse_failed", error=str(exc)[:200])
        return None


async def stream_klines(
    symbols_binance: list[str],
    interval:        str,
) -> AsyncIterator[Kline]:
    """
    Yield klines indefinitely. Reconnects on failure with backoff.

    Caller controls cancellation: wrap in `async for k in stream_klines(...):`
    inside a task — cancelling the task closes the socket cleanly.
    """
    streams = "/".join(f"{s.lower()}@kline_{interval}" for s in symbols_binance)
    url     = f"{settings.market_data_binance_ws_url}?streams={streams}"

    backoff = 1.0
    while True:
        try:
            log.info("binance_ws.connecting", url=url)
            async with websockets.connect(
                url,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=5,
                max_size=2**20,
            ) as ws:
                log.info("binance_ws.connected", symbols=symbols_binance, interval=interval)
                backoff = 1.0
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    kline = _parse_kline_msg(msg)
                    if kline is not None:
                        yield kline

        except asyncio.CancelledError:
            log.info("binance_ws.cancelled")
            raise
        except (ConnectionClosed, OSError) as exc:
            log.warning("binance_ws.disconnect", error=str(exc)[:200])
        except Exception as exc:
            log.exception("binance_ws.error", error=str(exc)[:300])

        await asyncio.sleep(backoff)
        backoff = min(backoff * 2.0, 30.0)
