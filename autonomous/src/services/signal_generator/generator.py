"""
Paper-trading signal generator.

Tick (every `signal_seeder_interval_seconds`):
  1. Read kill switch from platform_settings. If off → pause.
  2. Read market-data feed staleness. If stale → pause.
  3. Load active paper bots.
  4. For each (bot, symbol) pair where:
        - the symbol is supported (any BASE/USDT pair), AND
        - no pending or processing signal already exists, AND
        - the strategy-specific cooldown has elapsed since the last signal, AND
        - a fresh market_snapshot is available,
     insert one `signals` row with `signal_type='system'` and
     `direction='neutral'` so the Agent Engine claims it on its next poll.

The generator is paper-only. `is_eligible_paper_bot()` rejects live/shadow
bots and paused/archived bots. The autonomous service NEVER seeds live work.

Cadence defaults (configurable via env):
  scalping       →  2 min
  momentum       → 10 min
  trend_following→ 30 min
  mean_reversion → 15 min
  balanced       → 15 min
  (default)      →  5 min
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from src.config import settings
from src.db.repositories import (
    BotRepository,
    MarketSnapshotRepository,
    PaperAccountStatusRepository,
    PlatformSettingsRepository,
    SignalRepository,
)
from src.heartbeat import tracker
from src.logging_config import get_logger
from src.services.market_data.cache  import MarketDataCache
from src.services.market_data.health import is_feed_stale
from src.services.signal_generator.filters import (
    is_eligible_paper_bot,
    is_supported_symbol,
)
from src.worker import Worker

log = get_logger(__name__)


class SignalGenerator(Worker):
    name             = "signal_generator"
    interval_seconds = float(settings.signal_seeder_interval_seconds)

    def __init__(
        self,
        cache: MarketDataCache,
        bot_repo:           BotRepository | None = None,
        signal_repo:        SignalRepository | None = None,
        snapshot_repo:      MarketSnapshotRepository | None = None,
        platform_repo:      PlatformSettingsRepository | None = None,
        paper_status_repo:  PaperAccountStatusRepository | None = None,
    ) -> None:
        super().__init__()
        self.cache              = cache
        self.bot_repo           = bot_repo           or BotRepository()
        self.signal_repo        = signal_repo        or SignalRepository()
        self.snapshot_repo      = snapshot_repo      or MarketSnapshotRepository()
        self.platform_repo      = platform_repo      or PlatformSettingsRepository()
        self.paper_status_repo  = paper_status_repo  or PaperAccountStatusRepository()

    def _log_gate_snapshot(
        self,
        *,
        platform_enabled: bool,
        paper_account_found: bool,
        paper_account_status: str,
        bots_found: int,
        market_snapshot_found: bool,
        symbols: list[str],
        user_id: str | None,
    ) -> None:
        log.info(
            "signal.gates",
            platform_enabled=platform_enabled,
            paper_account_found=paper_account_found,
            paper_account_status=paper_account_status,
            bots_found=bots_found,
            market_snapshot_found=market_snapshot_found,
            symbols=symbols,
            user_id=user_id,
        )

    async def tick(self) -> None:
        # ── 1. Kill switch ────────────────────────────────────────────────────
        try:
            enabled = await self.platform_repo.global_trading_enabled()
        except Exception as exc:
            # PlatformSettingsRepository already fails-closed to False on error,
            # but defend anyway: pause if anything bubbles up.
            log.error("signal_gen.kill_switch_check_failed", error=str(exc)[:200])
            self.beat_paused(reason="kill_switch_check_error")
            return
        if not enabled:
            log.info("signal.skip.platform_disabled", platform_enabled=False)
            self.beat_paused(reason="kill_switch_off")
            return

        # ── 2. Market-data freshness ──────────────────────────────────────────
        if is_feed_stale(self.cache):
            self.beat_paused(reason="market_data_stale")
            return

        # ── 3. Load active paper bots ─────────────────────────────────────────
        try:
            bots = await self.bot_repo.list_active_paper_bots()
        except Exception as exc:
            log.exception("signal_gen.bot_list_failed", error=str(exc)[:300])
            tracker.beat(self.name, "error", error=str(exc)[:200])
            return

        eligible = [b for b in bots if is_eligible_paper_bot(b)]
        if not eligible:
            log.info(
                "signal.skip.no_bots",
                platform_enabled=enabled,
                bots_found=0,
            )
            self.beat_ok(eligible_bots=0, signals_seeded=0)
            return

        # ── 4. Seed signals ───────────────────────────────────────────────────
        # Strategy → minimum minutes between consecutive signals.
        cadence_map: dict[str, int] = {
            "scalping":        settings.signal_cadence_scalping_m,
            "momentum":        settings.signal_cadence_momentum_m,
            "trend_following": settings.signal_cadence_trend_m,
            "mean_reversion":  settings.signal_cadence_mean_reversion_m,
            "balanced":        settings.signal_cadence_balanced_m,
        }

        seeded     = 0
        considered = 0
        skipped    = {
            "unsupported_symbol":     0,
            "pending_exists":         0,
            "no_snapshot":            0,
            "paper_account_inactive": 0,
            "cooldown":               0,
        }

        # Per-user paper-account status cache for this tick.
        paper_status_for_user: dict[str, str] = {}

        for bot in eligible:
            user_id        = bot.get("user_id")
            bot_id         = bot.get("id")
            exchange       = bot.get("exchange") or "binance"
            trading_pairs  = bot.get("trading_pairs") or []
            if not user_id or not bot_id:
                self._log_gate_snapshot(
                    platform_enabled=enabled,
                    paper_account_found=False,
                    paper_account_status="missing",
                    bots_found=len(eligible),
                    market_snapshot_found=False,
                    symbols=list(trading_pairs),
                    user_id=user_id,
                )
                log.info(
                    "signal.skip.no_user",
                    bot_id=bot_id,
                    user_id=user_id,
                    symbols=list(trading_pairs),
                )
                continue

            # Per-user paper-account gate. status='active' is required.
            if user_id not in paper_status_for_user:
                paper_status_for_user[user_id] = await self.paper_status_repo.status(user_id)
            paper_status = paper_status_for_user[user_id]
            if paper_status not in ("active",):
                skipped["paper_account_inactive"] += len(trading_pairs)
                self._log_gate_snapshot(
                    platform_enabled=enabled,
                    paper_account_found=paper_status != "missing",
                    paper_account_status=paper_status,
                    bots_found=len(eligible),
                    market_snapshot_found=False,
                    symbols=list(trading_pairs),
                    user_id=user_id,
                )
                log.info(
                    "signal.skip.paper_account_inactive",
                    bot_id=bot_id,
                    user_id=user_id,
                    paper_account_found=paper_status != "missing",
                    paper_account_status=paper_status,
                    symbols=list(trading_pairs),
                )
                continue

            # ── Bot strategy metadata ─────────────────────────────────────────
            strategy  = (
                bot.get("strategy_type")
                or bot.get("metadata", {}).get("strategy")
                or "balanced"
            )
            cooldown_m     = cadence_map.get(strategy, settings.signal_cadence_default_m)
            candles_req    = int(bot.get("candles_required") or 100)
            current_warmup = bot.get("warmup_status", "pending")
            now_utc        = datetime.now(timezone.utc)

            for symbol in trading_pairs:
                considered += 1
                if not is_supported_symbol(symbol):
                    skipped["unsupported_symbol"] += 1
                    log.info(
                        "signal.skip.unsupported_symbol",
                        bot_id=bot_id, user_id=user_id, symbol=symbol,
                    )
                    continue

                # ── Warmup tracking: count available candles ──────────────────
                # We count snapshots BEFORE deciding to seed, so the warmup
                # status is always up-to-date even on ticks that don't seed.
                try:
                    # Use a 7-day window so pre-fetched historical candles
                    # (inserted with their actual open_time as captured_at)
                    # are always counted, regardless of when the service started.
                    candles_available = await self.snapshot_repo.count_recent(
                        exchange, symbol,
                        settings.market_data_kline_interval,
                        since_minutes=7 * 24 * 60,
                    )
                except Exception as exc:
                    log.warning("signal_gen.candle_count_failed", error=str(exc)[:200])
                    candles_available = 0

                # Update warmup state for this bot if it changed.
                try:
                    warmup_pct = round(
                        (candles_available / candles_req * 100) if candles_req > 0 else 0.0, 1
                    )
                    if candles_available >= candles_req:
                        if current_warmup != "ready":
                            await self.bot_repo.update_warmup_status(
                                bot_id, "ready", candles_available,
                                warmup_completed_at=now_utc,
                            )
                            current_warmup = "ready"
                            log.info(
                                "warmup.completed",
                                bot_id=bot_id, user_id=user_id, symbol=symbol,
                                candles_available=candles_available,
                                candles_required=candles_req,
                                strategy=strategy,
                            )
                        else:
                            log.info(
                                "warmup.progress",
                                bot_id=bot_id, user_id=user_id, symbol=symbol,
                                candles_collected=candles_available,
                                candles_required=candles_req,
                                warmup_status="ready",
                                pct=100.0,
                            )
                    else:
                        new_status = "warming_up"
                        if current_warmup == "pending":
                            await self.bot_repo.update_warmup_status(
                                bot_id, new_status, candles_available,
                                warmup_started_at=now_utc,
                            )
                        elif current_warmup == "warming_up":
                            # Update the count every tick so the UI shows progress.
                            await self.bot_repo.update_warmup_status(
                                bot_id, new_status, candles_available,
                            )
                        current_warmup = new_status
                        log.info(
                            "warmup.progress",
                            bot_id=bot_id, user_id=user_id, symbol=symbol,
                            candles_collected=candles_available,
                            candles_required=candles_req,
                            warmup_status=current_warmup,
                            pct=warmup_pct,
                        )
                except Exception as exc:
                    log.warning("signal_gen.warmup_update_failed", error=str(exc)[:200])

                # Skip if a signal is already in flight for this bot+symbol.
                try:
                    inflight_count = await self.signal_repo.count_inflight(
                        bot_id, symbol,
                        max_age_minutes=settings.signal_seeder_max_age_minutes,
                    )
                    if inflight_count > 0:
                        skipped["pending_exists"] += 1
                        log.info(
                            "signal.skip.duplicate_pending_signal",
                            bot_id=bot_id, user_id=user_id, symbol=symbol,
                            count=inflight_count,
                        )
                        continue
                except Exception as exc:
                    log.error("signal_gen.has_pending_failed", error=str(exc)[:200])
                    continue

                # ── Strategy-specific cooldown check ─────────────────────────
                try:
                    last_at = await self.signal_repo.last_completed_at(bot_id, symbol)
                    if last_at is not None:
                        elapsed_m = (now_utc - last_at).total_seconds() / 60.0
                        next_at   = last_at + timedelta(minutes=cooldown_m)
                        if elapsed_m < cooldown_m:
                            skipped["cooldown"] += 1
                            log.info(
                                "signal.skip.cooldown",
                                bot_id=bot_id, user_id=user_id, symbol=symbol,
                                strategy=strategy,
                                cooldown_minutes=cooldown_m,
                                elapsed_minutes=round(elapsed_m, 1),
                                next_signal_at=next_at.isoformat(),
                            )
                            continue
                except Exception as exc:
                    log.warning("signal_gen.cooldown_check_failed", error=str(exc)[:200])

                # Fetch the latest snapshot ID — required for downstream agents.
                try:
                    snap = await self.snapshot_repo.latest(
                        exchange=exchange, symbol=symbol,
                        timeframe=settings.market_data_kline_interval,
                    )
                except Exception as exc:
                    log.error("signal_gen.snapshot_lookup_failed", error=str(exc)[:200])
                    continue

                if not snap:
                    skipped["no_snapshot"] += 1
                    self._log_gate_snapshot(
                        platform_enabled=enabled,
                        paper_account_found=True,
                        paper_account_status=paper_status,
                        bots_found=len(eligible),
                        market_snapshot_found=False,
                        symbols=[symbol],
                        user_id=user_id,
                    )
                    log.info(
                        "signal.skip.no_market_data",
                        bot_id=bot_id, user_id=user_id, symbol=symbol,
                    )
                    continue

                self._log_gate_snapshot(
                    platform_enabled=enabled,
                    paper_account_found=True,
                    paper_account_status=paper_status,
                    bots_found=len(eligible),
                    market_snapshot_found=True,
                    symbols=[symbol],
                    user_id=user_id,
                )
                try:
                    sid = await self.signal_repo.create_system(
                        user_id=user_id,
                        bot_id=bot_id,
                        exchange=exchange,
                        symbol=symbol,
                        market_snapshot_id=snap.get("id"),
                        worker_id=settings.autonomous_worker_id,
                    )
                    seeded += 1

                    # Persist cadence timestamps so the UI can show last/next scan.
                    next_signal_at = now_utc + timedelta(minutes=cooldown_m)
                    try:
                        await self.bot_repo.update_signal_timestamps(
                            bot_id,
                            last_signal_at=now_utc,
                            next_signal_at=next_signal_at,
                        )
                    except Exception as exc:
                        log.warning("signal_gen.timestamp_update_failed", error=str(exc)[:200])

                    log.info(
                        "signal.created",
                        signal_id=sid,
                        bot_id=bot_id, user_id=user_id, symbol=symbol,
                        snapshot_id=snap.get("id"),
                        strategy=strategy,
                        next_signal_at=next_signal_at.isoformat(),
                    )
                except Exception as exc:
                    log.exception("signal_gen.create_failed", error=str(exc)[:300])

        self.beat_ok(
            eligible_bots=len(eligible),
            considered=considered,
            signals_seeded=seeded,
            skipped=skipped,
        )
