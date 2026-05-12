"""
PGMQ-based queue consumer (optional).

Falls back to PollingConsumer when USE_PGMQ=false (the default).
When PGMQ is enabled, messages are read from a Supabase PGMQ queue named
'trade_decisions_ready'. The Agent Engine or an approval Edge Function pushes
approved decision IDs into the queue.

This consumer does NOT replace the atomic DB claim in repositories.py.
It is an additional signalling layer to reduce polling latency.

TODO: Full PGMQ integration requires the pgmq extension to be enabled in
      Supabase and the queue to be seeded by the Agent Engine or approval webhook.
"""
from __future__ import annotations

from typing import AsyncIterator

from src.db.models import TradeDecision
from src.logging_config import get_logger
from src.queue.base import BaseQueueConsumer
from src.queue.polling import PollingConsumer

log = get_logger(__name__)

# TODO: Implement real PGMQ consumer when pgmq extension is available.
# For now, fall back to the polling consumer transparently.
PGMQConsumer = PollingConsumer


def build_consumer() -> BaseQueueConsumer:
    """
    Returns the configured consumer based on USE_PGMQ setting.
    Currently always returns PollingConsumer pending PGMQ integration.
    """
    from src.config import settings
    if settings.use_pgmq:
        log.warning(
            "pgmq.fallback",
            reason="PGMQ not yet implemented; using PollingConsumer",
        )
    return PollingConsumer()
