"""Notification stubs — fire-and-forget, never raise."""
from __future__ import annotations

from src.db.models import Trade
from src.logging_config import get_logger

log = get_logger(__name__)


class NotificationService:

    async def trade_closed(self, *, trade: Trade, reason: str) -> None:
        log.info(
            "notification.trade_closed",
            user_id=trade.user_id,
            trade_id=trade.id,
            symbol=trade.symbol,
            mode=trade.mode,
            reason=reason,
            realized_pnl=trade.realized_pnl,
        )
        # TODO: send push/email/realtime

    async def emergency_triggered(self, *, trade: Trade, reason: str) -> None:
        log.warning(
            "notification.emergency_triggered",
            user_id=trade.user_id,
            trade_id=trade.id,
            reason=reason[:300],
        )
        # TODO: CRITICAL alert channel

    async def reconciliation_required(self, *, trade: Trade, reason: str) -> None:
        log.error(
            "notification.reconciliation_required",
            user_id=trade.user_id,
            trade_id=trade.id,
            reason=reason[:300],
        )
        # TODO: admin notification

    async def pnl_updated(self, *, trade: Trade, pnl: float) -> None:
        log.debug(
            "notification.pnl_updated",
            trade_id=trade.id,
            unrealized_pnl=pnl,
        )
