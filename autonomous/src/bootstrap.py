"""
Demo-bot bootstrap.

On every iteration:
  1. If `bots` already has rows → nothing to do.
  2. Find the first user via the Supabase admin API. If none yet → log + retry.
  3. Ensure a `user_settings` row exists (idempotent).
  4. Create three paper bots:
        - BTC Momentum
        - ETH Trend
        - SOL Scalper
     all with `mode='paper'`, `status='active'`, `is_archived=false`,
     `real_trading_enabled=false`. NEVER creates live or shadow bots.

Bootstrap is paper-only. It is also idempotent — once any bot exists it
becomes a no-op, so re-running the autonomous service never duplicates bots.
"""
from __future__ import annotations

from typing import Any

from src.config import settings
from src.db.repositories import (
    AuditLogRepository,
    BotRepository,
    PaperAccountStatusRepository,
    UserDirectoryRepository,
    UserSettingsRepository,
)
from src.heartbeat import tracker
from src.logging_config import get_logger
from src.utils.time import utcnow_iso
from src.worker import Worker

log = get_logger(__name__)

HEARTBEAT_NAME = "bootstrap"


# Paper-only specs. Do NOT add live entries here.
DEMO_BOT_SPECS: list[dict[str, Any]] = [
    {
        "name":                  "BTC Momentum",
        "trading_pairs":         ["BTC/USDT"],
        "max_open_positions":    3,
        "max_position_size_pct": 10.0,
        "risk_per_trade_pct":    1.5,
        "max_daily_loss_pct":    3.0,
        "trailing_stop_pct":     2.0,
        "metadata": {
            "demo":     True,
            "strategy": "momentum",
            "created_by": "autonomous_bootstrap",
        },
    },
    {
        "name":                  "ETH Trend",
        "trading_pairs":         ["ETH/USDT"],
        "max_open_positions":    2,
        "max_position_size_pct": 8.0,
        "risk_per_trade_pct":    1.0,
        "max_daily_loss_pct":    2.5,
        "trailing_stop_pct":     1.5,
        "metadata": {
            "demo":     True,
            "strategy": "trend_following",
            "created_by": "autonomous_bootstrap",
        },
    },
    {
        "name":                  "SOL Scalper",
        "trading_pairs":         ["SOL/USDT"],
        "max_open_positions":    1,
        "max_position_size_pct": 5.0,
        "risk_per_trade_pct":    0.5,
        "max_daily_loss_pct":    1.5,
        "trailing_stop_pct":     1.0,
        "metadata": {
            "demo":     True,
            "strategy": "scalping",
            "created_by": "autonomous_bootstrap",
        },
    },
]


def _materialise_spec(spec: dict[str, Any], user_id: str) -> dict[str, Any]:
    """Combine a static spec with safe defaults to form a `bots` row."""
    return {
        "user_id":                  user_id,
        "name":                     spec["name"],
        "status":                   "active",
        "mode":                     "paper",
        "requires_manual_approval": False,
        "max_open_positions":       spec["max_open_positions"],
        "max_position_size_pct":    spec["max_position_size_pct"],
        "risk_per_trade_pct":       spec["risk_per_trade_pct"],
        "max_daily_loss_pct":       spec["max_daily_loss_pct"],
        "base_currency":            "USDT",
        "trading_pairs":            spec["trading_pairs"],
        "is_archived":              False,
        "metadata": {
            **spec["metadata"],
            "exchange": "binance",
            "trailing_stop_pct": spec["trailing_stop_pct"],
            "real_trading_enabled": False,
        },
    }


class DemoBootstrap(Worker):
    name             = HEARTBEAT_NAME
    interval_seconds = float(settings.demo_bootstrap_interval_seconds)

    def __init__(
        self,
        bot_repo:           BotRepository | None = None,
        user_directory:     UserDirectoryRepository | None = None,
        user_settings_repo: UserSettingsRepository | None = None,
        paper_status_repo:  PaperAccountStatusRepository | None = None,
        audit_repo:         AuditLogRepository | None = None,
    ) -> None:
        super().__init__()
        self.bot_repo           = bot_repo           or BotRepository()
        self.user_directory     = user_directory     or UserDirectoryRepository()
        self.user_settings_repo = user_settings_repo or UserSettingsRepository()
        self.paper_status_repo  = paper_status_repo  or PaperAccountStatusRepository()
        self.audit_repo         = audit_repo         or AuditLogRepository()
        self._already_bootstrapped: bool = False

    async def tick(self) -> None:
        if not settings.demo_bootstrap_enabled:
            self.beat_paused(reason="disabled_by_config")
            return

        if self._already_bootstrapped:
            self.beat_ok(state="completed")
            return

        # 1. Skip if any bot already exists (also catches concurrent bootstraps).
        try:
            existing = await self.bot_repo.count_all()
        except Exception as exc:
            log.error("bootstrap.count_failed", error=str(exc)[:200])
            tracker.beat(self.name, "error", error=str(exc)[:200])
            return

        if existing > 0:
            existing_user_id = await self.user_directory.first_user_id()
            if existing_user_id:
                account_status = await self.paper_status_repo.ensure_active(existing_user_id)
                log.info(
                    "bootstrap.paper_account_activated",
                    user_id=existing_user_id,
                    paper_account_status=account_status,
                    reason="bots_already_exist",
                )
            self._already_bootstrapped = True
            self.beat_ok(state="skipped_bots_exist", existing=existing)
            return

        # 2. Need a user to attach the bots to.
        user_id = await self.user_directory.first_user_id()
        if not user_id:
            self.beat_paused(reason="no_users_yet")
            return

        # 3. Ensure user_settings row.
        await self.user_settings_repo.ensure_exists(user_id)
        account_status = await self.paper_status_repo.ensure_active(user_id)
        log.info("bootstrap.paper_account_activated", user_id=user_id, paper_account_status=account_status)

        # 4. Create the three paper bots.
        if settings.dry_run:
            log.info("bootstrap.dry_run_skip", user_id=user_id, count=len(DEMO_BOT_SPECS))
            self._already_bootstrapped = True
            self.beat_ok(state="dry_run_skipped")
            return

        created_ids: list[str] = []
        for spec in DEMO_BOT_SPECS:
            row = _materialise_spec(spec, user_id)
            try:
                bot_id = await self.bot_repo.insert(row)
                created_ids.append(bot_id)
                log.info("bootstrap.bot_created", bot_id=bot_id, name=spec["name"], user_id=user_id)
            except Exception as exc:
                log.exception("bootstrap.bot_insert_failed", name=spec["name"], error=str(exc)[:300])

        # 5. Audit (best-effort).
        await self.audit_repo.create({
            "user_id":    user_id,
            "action":     "demo_bots_bootstrapped",
            "table_name": "bots",
            "source":     "autonomous_bootstrap",
            "metadata":   {
                "bot_ids":     created_ids,
                "count":       len(created_ids),
                "worker_id":   settings.autonomous_worker_id,
                "occurred_at": utcnow_iso(),
            },
        })

        self._already_bootstrapped = bool(created_ids)
        self.beat_ok(state="created", count=len(created_ids))
