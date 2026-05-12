"""
RecoveryService — handles partial failure scenarios.

Partial failure scenario:
  1. Live order placed on exchange → exchange returns FILLED
  2. Trade row created in DB        → success
  3. decision.linked_trade_id update fails (network blip)

On the next execution attempt, the Phase 2 atomic claim will succeed
(linked_trade_id is still NULL). The IdempotencyChecker then finds the
existing trade, calls recovery_for_existing_trade(), and the engine
links the decision to the existing trade without placing a second order.

Other recovery scenarios:
  - 'executing' decisions stuck for > stale_minutes: handled by the
    release_stuck_executions() PostgreSQL function called by pg_cron.

This service handles the application-layer recovery only.
"""
from __future__ import annotations

from src.db.models import Trade, TradeDecision
from src.db.repositories import TradeDecisionRepository, TradeEventRepository
from src.logging_config import get_logger

log = get_logger(__name__)


class RecoveryService:

    def __init__(self) -> None:
        self._decision_repo = TradeDecisionRepository()
        self._event_repo    = TradeEventRepository()

    async def recover_existing_trade(
        self,
        *,
        decision: TradeDecision,
        existing_trade: Trade,
    ) -> None:
        """
        Called when IdempotencyChecker finds a trade already created for
        this decision.

        Links the decision to the existing trade and writes a recovery event.
        This handles the case where the trade was created but the decision
        update failed.
        """
        log.warning(
            "recovery.linking_existing_trade",
            decision_id=decision.id,
            trade_id=existing_trade.id,
            trade_status=existing_trade.status,
            trade_mode=existing_trade.mode,
        )

        # Link the decision to the existing trade
        await self._decision_repo.mark_executed(
            decision_id=decision.id,
            trade_id=existing_trade.id,
        )

        # Write a recovery event for audit purposes
        from src.db.models import TradeEventInsert
        await self._event_repo.create(TradeEventInsert(
            trade_id=existing_trade.id,
            trade_decision_id=decision.id,
            bot_id=decision.bot_id,
            user_id=decision.user_id,
            event_type="recovery_linked_existing_trade",
            details={
                "recovered": True,
                "note": (
                    "Trade existed but decision.linked_trade_id was null. "
                    "Linked during recovery pass."
                ),
                "existing_trade_status": existing_trade.status,
            },
        ))

        log.info(
            "recovery.done",
            decision_id=decision.id,
            trade_id=existing_trade.id,
        )
