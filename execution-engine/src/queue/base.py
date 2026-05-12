"""Abstract queue consumer interface for the Execution Engine."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from src.db.models import TradeDecision


class BaseQueueConsumer(ABC):
    """
    Abstract consumer that yields claimed TradeDecision objects.

    The consumer is responsible for the two-phase claim:
      1. Fetch candidate IDs (non-locking)
      2. Atomically claim each ID

    Only claimed decisions are yielded. The caller (ExecutionEngine)
    is responsible for calling ack() or nack() on each yielded decision.
    """

    @abstractmethod
    async def consume(self) -> AsyncIterator[TradeDecision]:
        """Yields claimed TradeDecision instances."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Signal the consumer to stop after the current iteration."""
        ...
