"""
IdempotencyChecker — prevents duplicate trade creation.

Two independent guards:
  1. decision.linked_trade_id IS NULL (checked during Phase 2 atomic claim)
  2. SELECT FROM trades WHERE trade_decision_id = X (explicit DB check)

Guard 1 runs at claim time (enforced by DB UPDATE condition).
Guard 2 runs here before creating the trade row, as a defence-in-depth check.

If a trade already exists for this decision_id, the engine reuses the existing
trade_id rather than creating a duplicate — this handles the case where the
trade was created but the decision update failed (partial failure recovery).
"""
from __future__ import annotations

from typing import Optional

from src.db.models import Trade
from src.db.repositories import TradeRepository
from src.logging_config import get_logger

log = get_logger(__name__)


class IdempotencyChecker:
    """
    Prevents duplicate trade creation for the same trade_decision_id.

    Usage:
        checker = IdempotencyChecker()
        existing = await checker.find_existing_trade(decision_id)
        if existing:
            # reuse existing trade — do NOT create a new one
            return existing
    """

    def __init__(self) -> None:
        self._repo = TradeRepository()

    async def find_existing_trade(
        self, trade_decision_id: str
    ) -> Optional[Trade]:
        """
        Returns an existing Trade if one was already created for this decision,
        or None if no trade exists yet.

        Callers MUST check this before creating a new trade. If an existing trade
        is found, mark the decision as executed with that trade_id instead of
        creating a duplicate.
        """
        existing = await self._repo.find_by_decision_id(trade_decision_id)

        if existing:
            log.warning(
                "idempotency.duplicate_prevented",
                decision_id=trade_decision_id,
                existing_trade_id=existing.id,
                trade_status=existing.status,
            )

        return existing
