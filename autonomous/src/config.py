"""
Autonomous service configuration. Validated at startup; fail-closed on
missing required secrets.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Supabase ──────────────────────────────────────────────────────────────
    supabase_url:              str
    supabase_service_role_key: str

    # ── Worker / logging ──────────────────────────────────────────────────────
    autonomous_worker_id: str = "auto-local"
    log_level:            str = "INFO"
    dry_run:              bool = False

    # ── Market data ───────────────────────────────────────────────────────────
    market_data_symbols:               str   = "BTCUSDT,ETHUSDT,SOLUSDT"
    market_data_symbol_universe:       str   = "binance_all_usdt"
    market_data_kline_interval:        str   = "1m"
    market_data_rest_fallback_seconds: float = Field(default=30.0, ge=5.0)
    market_data_heartbeat_seconds:     float = Field(default=30.0, ge=5.0)
    market_data_stale_after_seconds:   float = Field(default=120.0, ge=30.0)
    market_data_prefetch_concurrency:  int   = Field(default=12, ge=1, le=50)
    market_data_binance_ws_url:        str   = "wss://stream.binance.com:9443/stream"
    market_data_binance_rest_url:      str   = "https://api.binance.com"

    # ── Signal seeder ─────────────────────────────────────────────────────────
    signal_seeder_interval_seconds: float = Field(default=60.0, ge=10.0)
    signal_seeder_max_age_minutes:  int   = Field(default=5,    ge=1)

    # Minimum minutes between consecutive seeded signals per (bot, symbol),
    # keyed by strategy_type. Prevents spam and respects strategy cadence.
    signal_cadence_scalping_m:     int = Field(default=30,  ge=1)
    signal_cadence_momentum_m:     int = Field(default=90,  ge=1)
    signal_cadence_trend_m:        int = Field(default=240, ge=1)
    signal_cadence_mean_reversion_m: int = Field(default=120, ge=1)
    signal_cadence_balanced_m:     int = Field(default=180, ge=1)
    signal_cadence_default_m:      int = Field(default=120, ge=1)
    signal_scan_all_market_symbols: bool = False
    signal_max_symbols_per_bot_tick: int = Field(default=10, ge=1, le=1000)
    futures_min_signal_cadence_m:   int = Field(default=120, ge=1)
    portfolio_min_signal_cadence_m: int = Field(default=360, ge=1)

    # ── Demo-bot bootstrap ────────────────────────────────────────────────────
    demo_bootstrap_enabled:          bool  = True
    demo_bootstrap_interval_seconds: float = Field(default=30.0, ge=5.0)

    # ── Telegram signal ingestion ───────────────────────────────────────────
    telegram_ingestion_enabled: bool = False
    telegram_api_id: Optional[int] = None
    telegram_api_hash: Optional[str] = None
    telegram_session_string: Optional[str] = None
    telegram_listener_reload_seconds: float = Field(default=60.0, ge=10.0)
    telegram_api_cors_origin: str = "http://localhost:3001"

    # ── Health server ─────────────────────────────────────────────────────────
    health_port: int = Field(default=9090, ge=1, le=65535)

    @property
    def symbols(self) -> list[str]:
        return [s.strip().upper() for s in self.market_data_symbols.split(",") if s.strip()]


settings = Settings()
