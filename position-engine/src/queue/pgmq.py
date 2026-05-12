"""
PgmqTradePoller — stub for pgmq-backed trade polling.

pgmq (PostgreSQL Message Queue) provides at-least-once delivery semantics
with automatic message visibility timeouts. This is an alternative to the
direct DB polling strategy in PollingTradePoller.

TODO: Implement pgmq integration when USE_PGMQ=true.
      For now this stub falls back to PollingTradePoller.

Docs: https://github.com/tembo-io/pgmq
"""
from __future__ import annotations

from typing import AsyncIterator

from src.db.models import Trade
from src.logging_config import get_logger
from src.queue.base import TradePoller
from src.queue.polling import PollingTradePoller

log = get_logger(__name__)

_QUEUE_NAME = "position_lifecycle"


class PgmqTradePoller(TradePoller):
    """
    pgmq-backed trade poller.

    Falls back to PollingTradePoller until pgmq is configured.
    """

    def __init__(self) -> None:
        log.warning(
            "pgmq.not_implemented",
            message=(
                "PgmqTradePoller is a stub. "
                "Falling back to PollingTradePoller. "
                "Set USE_PGMQ=false to suppress this warning."
            ),
        )
        self._delegate = PollingTradePoller()
        self._stopped  = False

    async def __aenter__(self) -> "PgmqTradePoller":
        await self._delegate.__aenter__()
        return self

    async def __aexit__(self, *args) -> None:
        await self._delegate.__aexit__(*args)
        self._stopped = True

    async def poll(self) -> AsyncIterator[Trade]:
        # TODO: replace with actual pgmq read + visibility lock
        async for trade in self._delegate.poll():
            if self._stopped:
                return
            yield trade

    def stop(self) -> None:
        self._stopped = True
        self._delegate.stop()
