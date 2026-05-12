"""
RecoveryService — handles partial close failure scenarios.

If a close order was submitted to the exchange but the DB write failed,
the trade's lifecycle_status is 'closing' with close_order_id set.
On the next monitoring cycle, the engine detects the partial state and
calls this service to verify the close order status and complete recovery.

NEVER blindly close or re-open. If the close order status is ambiguous,
mark needs_reconciliation and alert.
"""
from __future__ import annotations

from src.db.models import Trade
from src.db.repositories import (
    AuditLogInsert,
    AuditLogRepository,
    SecurityLogInsert,
    SecurityLogRepository,
    TradeEventInsert,
    TradeEventRepository,
    TradeLifecycleRepository,
)
from src.db.models import SeverityLevel
from src.logging_config import get_logger

log = get_logger(__name__)


class RecoveryService:
    def __init__(self) -> None:
        self._lifecycle_repo = TradeLifecycleRepository()
        self._event_repo     = TradeEventRepository()
        self._security_log   = SecurityLogRepository()
        self._audit_log      = AuditLogRepository()

    async def handle_stuck_closing(self, trade: Trade) -> None:
        """
        Called when a trade is found in lifecycle_status='closing' at claim time.

        This means a close order was submitted but not confirmed.
        We cannot blindly retry — mark needs_reconciliation.
        """
        log.warning(
            "recovery.stuck_closing",
            trade_id=trade.id,
            close_order_id=trade.close_order_id,
        )

        await self._security_log.create(SecurityLogInsert(
            user_id=trade.user_id,
            event_type="exchange_order_unknown",
            severity=SeverityLevel.CRITICAL.value,
            source="position_engine",
            message=(
                f"Trade {trade.id} found in 'closing' state with no confirmed fill. "
                f"Close order ID: {trade.close_order_id or 'unknown'}. "
                "Manual reconciliation required."
            ),
            metadata={"trade_id": trade.id, "close_order_id": trade.close_order_id},
        ))

        await self._event_repo.create(TradeEventInsert(
            trade_id=trade.id,
            trade_decision_id=trade.trade_decision_id,
            bot_id=trade.bot_id,
            user_id=trade.user_id,
            event_type="reconciliation_required",
            details={
                "reason":         "Stuck in closing state — close order not confirmed",
                "close_order_id": trade.close_order_id,
            },
        ))

        await self._lifecycle_repo.mark_needs_reconciliation(
            trade.id,
            reason="Stuck in closing state — close order not confirmed. Manual review required.",
        )
