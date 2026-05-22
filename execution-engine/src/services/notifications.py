"""
NotificationService — user-facing alerts for trade events.

Current implementation: stub with structured logging.
TODO: Integrate with a real notification backend (Supabase Realtime, email,
      push notifications, Slack webhook, etc.) before production.

All methods are fire-and-forget: failures are logged but never raise.
"""
from __future__ import annotations

from src.db.models import Trade, TradeDecision
from src.db.supabase_client import get_client
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
        try:
            stop_loss = f"{trade.stop_loss:.8g}" if trade.stop_loss else "-"
            take_profit = f"{trade.take_profit:.8g}" if trade.take_profit else "-"
            message = (
                f"{trade.direction.upper()} {trade.symbol} işlemi {trade.entry_price:.8g} giriş fiyatıyla açıldı. "
                f"Miktar {trade.quantity:.8g}, notional ${(trade.notional or trade.entry_price * trade.quantity):.2f}, "
                f"SL {stop_loss}, "
                f"TP {take_profit}, "
                f"1R ${(trade.risk_amount or 0):.2f}."
            )
        except Exception:
            message = f"{trade.direction.upper()} {trade.symbol} işlemi açıldı."

        try:
            get_client().table("notifications").insert({
                "user_id": decision.user_id,
                "type": "trade_opened",
                "title": "İşlem açıldı",
                "message": message,
                "is_read": False,
                "related_table": "trades",
                "related_id": trade.id,
                "priority": 2,
                "metadata": {
                    "trade_id": trade.id,
                    "symbol": trade.symbol,
                    "direction": trade.direction,
                    "side": trade.side,
                    "mode": trade.mode,
                    "entry_price": trade.entry_price,
                    "quantity": trade.quantity,
                    "notional": trade.notional,
                    "stop_loss": trade.stop_loss,
                    "take_profit": trade.take_profit,
                    "risk_amount": trade.risk_amount,
                    "risk_percent": trade.risk_percent,
                },
            }).execute()
        except Exception as exc:
            log.warning("notification.trade_opened_insert_failed", error=str(exc)[:200])

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
