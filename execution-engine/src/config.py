"""
Execution Engine configuration — loaded from environment variables.

All settings are typed and validated at startup.
If a required variable is missing, the engine fails to start (fail-closed).
"""
from __future__ import annotations

import uuid
from pathlib import Path

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
    supabase_url: str
    supabase_service_role_key: str

    # ── API Key Encryption ────────────────────────────────────────────────────
    api_key_encryption_secret: str

    # ── Live Execution Gate ───────────────────────────────────────────────────
    # KEEP FALSE until fully audited. Only set true after all safety reviews.
    enable_live_execution: bool = False

    # ── Worker Identity ───────────────────────────────────────────────────────
    worker_id: str = Field(
        default_factory=lambda: f"exec-{uuid.uuid4().hex[:8]}"
    )

    # ── Polling ───────────────────────────────────────────────────────────────
    poll_interval_seconds: float = Field(default=5.0, ge=1.0)
    max_concurrent_runs: int = Field(default=3, ge=1)
    max_retries: int = Field(default=3, ge=0)
    stale_minutes: int = Field(default=10, ge=1)
    pipeline_timeout_seconds: float = Field(default=120.0, ge=10.0)

    # ── Queue ─────────────────────────────────────────────────────────────────
    use_pgmq: bool = False

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = "INFO"

    # ── Dry Run ───────────────────────────────────────────────────────────────
    # true = run all logic but skip DB writes and exchange calls
    dry_run: bool = False

    # ── Risk Defaults ─────────────────────────────────────────────────────────
    decision_stale_minutes: int = Field(default=60, ge=1)
    max_slippage_pct: float = Field(default=1.0, ge=0.0)
    max_spread_pct: float = Field(default=2.0, ge=0.0)
    require_stop_loss_live: bool = True
    paper_portfolio_value_usd: float = Field(default=10_000.0, ge=100.0)
    paper_default_max_leverage: float = Field(default=20.0, ge=1.0)
    paper_max_leverage_cap: float = Field(default=125.0, ge=1.0)
    binance_futures_exchange_info_url: str = (
        "https://fapi.binance.com/fapi/v1/exchangeInfo"
    )

    # ── Fetch batch size ──────────────────────────────────────────────────────
    fetch_batch_size: int = Field(default=5, ge=1)


settings = Settings()
