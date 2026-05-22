"""
Position Engine configuration — loaded from environment variables at startup.

Fail-closed: if a required variable is missing the process exits before
accepting any work.
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
    supabase_url:              str
    supabase_service_role_key: str

    # ── Encryption (for exchange API keys) ───────────────────────────────────
    api_key_encryption_secret: str

    # ── Worker identity ───────────────────────────────────────────────────────
    position_engine_worker_id: str = Field(
        default_factory=lambda: f"pos-{uuid.uuid4().hex[:8]}"
    )

    # ── Polling ───────────────────────────────────────────────────────────────
    position_poll_interval_seconds: float = Field(default=1.0, ge=1.0)
    position_max_concurrent_runs:   int   = Field(default=5, ge=1)
    position_stale_minutes:         int   = Field(default=10, ge=1)
    position_max_retries:           int   = Field(default=3, ge=0)

    # ── Live Close Gate ───────────────────────────────────────────────────────
    # CRITICAL: Keep false until all safety checks are audited.
    # Emergency closes additionally require platform_settings.emergency_close_enabled=true.
    enable_live_close: bool = False

    # ── Queue ─────────────────────────────────────────────────────────────────
    use_pgmq: bool = False

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = "INFO"

    # ── Dry Run ───────────────────────────────────────────────────────────────
    dry_run: bool = False

    # ── Timing ───────────────────────────────────────────────────────────────
    order_confirmation_timeout_seconds: float = Field(default=30.0, ge=5.0)
    fetch_batch_size:                   int   = Field(default=10, ge=1)
    platform_settings_cache_ttl_seconds: float = Field(default=30.0, ge=5.0)
    market_data_kline_interval:          str   = "1m"

    @property
    def worker_id(self) -> str:
        return self.position_engine_worker_id


settings = Settings()
