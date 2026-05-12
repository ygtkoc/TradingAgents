"""
Abstract base class for signal queue consumers.

Two implementations are provided:
  - PollingConsumer  (src/queue/polling.py) — polls the signals table directly
  - PgmqConsumer     (src/queue/pgmq.py)    — uses pgmq extension if available

The orchestrator is decoupled from the queue implementation.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional

from src.db.models import Signal


class BaseQueueConsumer(ABC):
    """
    Async context manager that yields claimed Signal instances.

    Usage:
        async with consumer:
            async for signal in consumer.consume():
                await process(signal)
    """

    @abstractmethod
    async def __aenter__(self) -> "BaseQueueConsumer":
        ...

    @abstractmethod
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        ...

    @abstractmethod
    async def consume(self) -> AsyncIterator[Signal]:
        """
        Yields claimed Signal instances one at a time.
        Blocks/polls until a signal is available.
        Must be an async generator.
        """
        ...

    @abstractmethod
    async def ack(self, signal: Signal) -> None:
        """Mark a signal as successfully processed."""
        ...

    @abstractmethod
    async def nack(self, signal: Signal, reason: str) -> None:
        """Return a signal to the queue (or mark as failed) with a reason."""
        ...
