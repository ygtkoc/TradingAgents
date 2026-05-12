"""
Centralised settings loaded from environment variables / .env file.
pydantic-settings validates types at startup — misconfigured deployments
fail immediately rather than at first signal processing cycle.
"""
from __future__ import annotations

import socket
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Supabase ────────────────────────────────────────────────────────────
    supabase_url: str
    supabase_service_role_key: str  # NEVER log this value

    # ── LLM keys (optional for MVP — agents fall back to rule-based logic) ─
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None

    # ── Engine behaviour ────────────────────────────────────────────────────
    poll_interval_seconds: int = Field(default=10, ge=2, le=300)
    max_concurrent_runs: int = Field(default=5, ge=1, le=50)
    agent_timeout_seconds: int = Field(default=15, ge=5, le=300)
    pipeline_timeout_seconds: int = Field(default=60, ge=30, le=600)
    use_pgmq: bool = False

    # When True, the engine runs the full pipeline but skips all DB writes.
    # Safe for development / testing without polluting production data.
    dry_run: bool = False

    # ── Worker identity ─────────────────────────────────────────────────────
    # Unique per process; used as processing_worker_id on signals to prevent
    # double-processing when running multiple replicas.
    worker_id: str = Field(default_factory=lambda: f"worker-{socket.gethostname()}")

    # ── Logging ─────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_json: bool = True   # False = pretty console output for development

    # ── Decision thresholds ─────────────────────────────────────────────────
    score_threshold_open: float = Field(default=70.0, ge=0.0, le=100.0)
    score_threshold_manual_review: float = Field(default=40.0, ge=0.0, le=100.0)

    # ── Risk circuit breakers ────────────────────────────────────────────────
    max_stale_snapshot_minutes: int = Field(default=15, ge=1, le=1440)
    manipulation_spread_threshold_pct: float = Field(default=2.0, ge=0.1, le=50.0)

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return upper

    @property
    def has_llm(self) -> bool:
        return bool(self.openai_api_key or self.anthropic_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
