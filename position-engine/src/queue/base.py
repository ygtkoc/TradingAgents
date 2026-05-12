"""
Abstract base class for the position-engine queue / trade poller.

The position engine doesn't consume a message queue the same way the
execution engine does. Instead it polls the trades table for open trades
whose lifecycle_status is 'idle' or 'needs_reconciliation', then
atomically claims each one for a monitoring cycle.

Subclasses implement the polling strategy (direct DB vs. pgmq).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from src.db.models import Trade


class TradePoller(ABC):
    """
    Abstract base for trade pollers.

    Usage (async context manager):

        async with MyPoller() as poller:
            async for trade in poller.poll():
                await engine.run(trade)
    """

    @abstractmethod
    async def __aenter__(self) -> "TradePoller":
        ...

    @abstractmethod
    async def __aexit__(self, *args) -> None:
        ...

    @abstractmethod
    async def poll(self) -> AsyncIterator[Trade]:
        """
        Yield atomically-claimed Trade objects.

        Only yields trades where the atomic claim succeeded.
        Caller is responsible for releasing or closing the trade.
        Never raises StopIteration — callers control the outer loop.
        """
        ...

    def stop(self) -> None:
        """Signal the poller to stop yielding on the next iteration."""
        self._stopped = True

    @property
    def stopped(self) -> bool:
        return getattr(self, "_stopped", False)
