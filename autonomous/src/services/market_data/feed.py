"""
Market data feed orchestrator.

Responsibilities:
  • Run a Binance WebSocket consumer.
  • If the WS goes silent for `market_data_rest_fallback_seconds`, poll REST.
  • On every observation:
      - Update the in-memory cache.
      - Heartbeat the tracker so /health reflects liveness.
      - When a candle closes, write a `market_snapshots` row.

The feed is paper-only and uses public Binance endpoints — no API keys.

Symbol tracking is dynamic: at startup the feed queries all active paper-bot
trading_pairs from the DB and merges them with the configured defaults. This
ensures user-created bots (e.g. DOGE/USDT) receive market data without any
manual configuration change.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Optional

from src.config import settings
from src.db.repositories import BotRepository, MarketSnapshotRepository
from src.heartbeat import tracker
from src.logging_config import get_logger
from src.services.market_data.binance_rest import fetch_kline_history, fetch_latest_kline
from src.services.market_data.binance_ws   import stream_klines
from src.services.market_data.cache        import MarketDataCache
from src.services.market_data.models       import INTERNAL_TO_BINANCE, Kline, to_binance, to_internal
from src.utils.time import utcnow_iso

log = get_logger(__name__)

HEARTBEAT_NAME = "market_data"


class MarketDataFeed:
    """Owns the market-data lifecycle for a single autonomous process."""

    def __init__(
        self,
        cache: MarketDataCache,
        snapshot_repo: Optional[MarketSnapshotRepository] = None,
        bot_repo: Optional[BotRepository] = None,
    ) -> None:
        self.cache         = cache
        self.snapshot_repo = snapshot_repo or MarketSnapshotRepository()
        self._bot_repo     = bot_repo      or BotRepository()
        self._last_ws_msg_m: float = 0.0
        tracker.register(HEARTBEAT_NAME)

    # ── Public entry points ──────────────────────────────────────────────────

    async def run(self) -> None:
        """Main loop. Runs WebSocket consumer; spawns a REST watchdog in
        parallel so the feed keeps producing snapshots even if the WS is
        slow or silent."""
        symbols_binance = await self._resolve_symbols()
        log.info(
            "feed.symbols_resolved",
            count=len(symbols_binance),
            symbols=symbols_binance,
        )

        # Pre-seed historical bars so the agent-engine risk assessors have
        # ≥ 50 bars immediately rather than waiting 50+ minutes for real-time
        # candles to accumulate. This is best-effort — errors are logged but
        # never prevent the WS loop from starting.
        await self._prefetch_history(symbols_binance)

        await asyncio.gather(
            self._ws_loop(symbols_binance),
            self._rest_watchdog(symbols_binance),
        )

    # ── Historical pre-seed ──────────────────────────────────────────────────

    async def _prefetch_history(self, symbols_binance: list[str]) -> None:
        """Fetch and store 150 historical klines per symbol so the risk agent
        has enough ATR/RSI bars from the very first pipeline tick.

        Skips a symbol if ≥ 50 snapshots already exist in the last 5 hours
        (short-circuit on quick service restarts to avoid duplicate rows).
        """
        interval = settings.market_data_kline_interval
        # Fetch 150 candles; after excluding the open candle we have 149 closed bars.
        fetch_limit = 150
        # Skip pre-fetch if this many snapshots already exist.
        sufficient  = 50
        # Look-back window for the "already sufficient" check.
        lookback_m  = 300   # 5 hours

        log.info(
            "feed.prefetch.start",
            symbols=symbols_binance,
            interval=interval,
            target_bars=fetch_limit,
        )

        for sym_binance in symbols_binance:
            try:
                internal = to_internal(sym_binance)
                if not internal:
                    continue

                existing = await self.snapshot_repo.count_recent(
                    "binance", internal, interval, since_minutes=lookback_m
                )
                if existing >= sufficient:
                    log.debug(
                        "feed.prefetch.skip",
                        symbol=sym_binance,
                        existing=existing,
                        reason="already_sufficient",
                    )
                    continue

                klines = await fetch_kline_history(sym_binance, interval, limit=fetch_limit)
                if not klines:
                    log.warning("feed.prefetch.empty", symbol=sym_binance)
                    continue

                rows = [
                    {
                        "exchange":    "binance",
                        "symbol":      k.symbol_internal,
                        "timeframe":   k.interval,
                        "open_price":  k.open,
                        "high_price":  k.high,
                        "low_price":   k.low,
                        "close_price": k.close,
                        "volume":      k.volume,
                        # Use open_time_ms as captured_at so history is ordered
                        # chronologically and agent queries return oldest-first.
                        "captured_at": datetime.fromtimestamp(
                            k.open_time_ms / 1000, tz=timezone.utc
                        ).isoformat(),
                        "source": "binance_rest_backfill",
                    }
                    for k in klines
                ]

                if not settings.dry_run:
                    await self.snapshot_repo.bulk_insert(rows)

                log.info(
                    "feed.prefetch.done",
                    symbol=sym_binance,
                    bars=len(rows),
                    interval=interval,
                )

            except Exception as exc:
                log.warning(
                    "feed.prefetch.error",
                    symbol=sym_binance,
                    error=str(exc)[:300],
                    hint="Pre-fetch is best-effort; WS loop will start regardless.",
                )

    # ── Symbol resolution ────────────────────────────────────────────────────

    async def _resolve_symbols(self) -> list[str]:
        """Build the Binance symbol list from configured defaults PLUS all
        active paper-bot trading pairs found in the database.

        Falls back gracefully: if the DB is unreachable, only the configured
        defaults are used (the feed still works for BTC/ETH/SOL).
        """
        # Start with configured defaults.
        from_config: set[str] = set()
        for s in settings.symbols:
            b = to_binance(s)
            if b:
                from_config.add(b)
        if not from_config:
            from_config = set(INTERNAL_TO_BINANCE.values())  # static fallback

        # Merge user bot trading pairs.
        from_bots: set[str] = set()
        try:
            pairs = await self._bot_repo.list_unique_trading_pairs()
            for internal_sym in pairs:
                b = to_binance(internal_sym)
                if b:
                    from_bots.add(b)
            if from_bots:
                log.info(
                    "feed.dynamic_bot_symbols",
                    bot_symbols=sorted(from_bots),
                    new_symbols=sorted(from_bots - from_config),
                )
        except Exception as exc:
            log.warning(
                "feed.bot_symbol_query_failed",
                error=str(exc)[:200],
                hint="Using configured defaults only",
            )

        return sorted(from_config | from_bots)

    # ── Private ──────────────────────────────────────────────────────────────

    async def _ws_loop(self, symbols_binance: list[str]) -> None:
        try:
            async for kline in stream_klines(symbols_binance, settings.market_data_kline_interval):
                self._last_ws_msg_m = time.monotonic()
                await self._on_kline(kline)
        except asyncio.CancelledError:
            log.info("feed.ws_cancelled")
            raise

    async def _rest_watchdog(self, symbols_binance: list[str]) -> None:
        """Polls REST when the WS is silent for too long. This both:
          • produces fresh snapshots during an outage, and
          • keeps the heartbeat fresh so the signal generator does not pause."""
        try:
            while True:
                await asyncio.sleep(settings.market_data_rest_fallback_seconds)

                if self._last_ws_msg_m == 0.0:
                    silent_for = float("inf")
                else:
                    silent_for = time.monotonic() - self._last_ws_msg_m

                if silent_for < settings.market_data_rest_fallback_seconds:
                    continue  # WS is healthy, skip REST poll

                log.warning("feed.ws_silent_falling_back_to_rest", silent_s=round(silent_for, 1))
                tracker.beat(HEARTBEAT_NAME, "degraded", source="rest", silent_s=round(silent_for, 1))

                for sym in symbols_binance:
                    kline = await fetch_latest_kline(sym, settings.market_data_kline_interval)
                    if kline is not None:
                        await self._on_kline(kline)

        except asyncio.CancelledError:
            log.info("feed.rest_watchdog_cancelled")
            raise

    async def _on_kline(self, kline: Kline) -> None:
        # 1. Cache the latest observation
        self.cache.update(kline)

        # 2. Persist closed candles only — open candles update the cache for
        #    fast access but do not pollute the snapshot history.
        if kline.is_closed:
            try:
                await self._write_snapshot(kline)
            except Exception as exc:
                log.exception(
                    "feed.snapshot_write_failed",
                    symbol=kline.symbol_internal,
                    error=str(exc)[:300],
                )

        # 3. Heartbeat
        tracker.beat(
            HEARTBEAT_NAME,
            "ok",
            source=kline.source,
            symbol=kline.symbol_internal,
            close=kline.close,
        )

    async def _write_snapshot(self, kline: Kline) -> None:
        if settings.dry_run:
            log.info("feed.dry_run_skip", symbol=kline.symbol_internal, close=kline.close)
            return

        row = {
            "exchange":    "binance",
            "symbol":      kline.symbol_internal,
            "timeframe":   kline.interval,
            "open_price":  kline.open,
            "high_price":  kline.high,
            "low_price":   kline.low,
            "close_price": kline.close,
            "volume":      kline.volume,
            "captured_at": utcnow_iso(),
            "source":      f"binance_{kline.source}",
        }
        snap_id = await self.snapshot_repo.insert(row)
        log.debug(
            "feed.snapshot_written",
            id=snap_id,
            symbol=kline.symbol_internal,
            close=kline.close,
            source=kline.source,
        )
