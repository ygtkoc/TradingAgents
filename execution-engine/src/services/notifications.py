"""
NotificationService — user-facing alerts for trade events.

Current implementation: stub with structured logging.
TODO: Integrate with a real notification backend (Supabase Realtime, email,
      push notifications, Slack webhook, etc.) before production.

All methods are fire-and-forget: failures are logged but never raise.
"""
from __future__ import annotations

from src.db.models import Trade, TradeDecision
from src.logging_config import get_logger

log = get_logger(__name__)


class NotificationService:

    async def trade_executed(
        self, *, decision: TradeDecision, trade: Trade
    ) -> None:
        """Notify user that a trade was executed."""
        log.info(
            "notification.trade_executed",
            user_id=decision.user_id,
            bot_id=decision.bot_id,
            trade_id=trade.id,
            symbol=trade.symbol,
            side=trade.side,
            mode=trade.mode,
            entry_price=trade.entry_price,
            quantity=trade.quantity,
        )
        # TODO: send push/email/realtime notification

    async def trade_skipped(
        self, *, decision: TradeDecision, reason: str
    ) -> None:
        """Notify user that a trade was blocked (risk/security guard)."""
        log.warning(
            "notification.trade_skipped",
            user_id=decision.user_id,
            bot_id=decision.bot_id,
            decision_id=decision.id,
            reason=reason[:300],
        )
        # TODO: send user-facing alert for blocked live trades

    async def trade_failed(
        self, *, decision: TradeDecision, error: str
    ) -> None:
        """Notify user of a trade execution failure."""
        log.error(
            "notification.trade_failed",
            user_id=decision.user_id,
            bot_id=decision.bot_id,
            decision_id=decision.id,
            error=error[:300],
        )
        # TODO: send CRITICAL alert for live trade failures

    async def live_gate_blocked(
        self, *, decision: TradeDecision
    ) -> None:
        """Notify that a live decision was blocked because ENABLE_LIVE_EXECUTION=False."""
        log.warning(
            "notification.live_gate_blocked",
            user_id=decision.user_id,
            bot_id=decision.bot_id,
            decision_id=decision.id,
            note="Set ENABLE_LIVE_EXECUTION=true to enable live trading",
        )
