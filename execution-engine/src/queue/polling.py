"""
DB polling queue consumer — two-phase atomic decision claiming.

Phase 1 — fetch_executable_ids(): SELECT ids of claimable decisions.
           Non-locking. Multiple workers can call this concurrently.
Phase 2 — claim_for_execution(): UPDATE WHERE id=X AND execution_status='pending_execution'
           RETURNING *. Atomic. If 0 rows → another worker claimed it → skip silently.

On transient failure:
  Leave decision in 'executing'. The release_stuck_executions() DB function
  (pg_cron, every 5 min) resets stuck decisions to 'pending_execution' with
  execution_retry_count++.

On permanent failure:
  Call engine.mark_failed() → execution_status='failed', never retried.
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

from src.config import settings
from src.db.models import TradeDecision
from src.db.repositories import TradeDecisionRepository
from src.logging_config import get_logger
from src.queue.base import BaseQueueConsumer

log = get_logger(__name__)


class PollingConsumer(BaseQueueConsumer):
    """
    Two-phase polling consumer for trade_decisions.

    Yields only successfully claimed decisions. The ExecutionEngine
    must mark each as executed/failed/skipped.
    """

    def __init__(self) -> None:
        self._repo = TradeDecisionRepository()
        self._running = False

    async def __aenter__(self) -> "PollingConsumer":
        self._running = True
        log.info(
            "polling_consumer.started",
            interval_s=settings.poll_interval_seconds,
            worker=settings.worker_id,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self._running = False
        log.info("polling_consumer.stopped")

    def stop(self) -> None:
        self._running = False

    async def consume(self) -> AsyncIterator[TradeDecision]:
        """
        Async generator — yields claimed TradeDecision instances.

        Backs off exponentially on empty polls to reduce DB load.
        """
        consecutive_empty = 0

        while self._running:
            try:
                ids = await self._repo.fetch_executable_ids(
                    limit=settings.fetch_batch_size
                )
            except Exception as exc:
                log.error("polling_consumer.fetch_error", error=str(exc))
                await asyncio.sleep(settings.poll_interval_seconds)
                continue

            if not ids:
                consecutive_empty += 1
                # Exponential back-off capped at 60 s
                sleep = min(
                    settings.poll_interval_seconds * min(consecutive_empty, 6), 60
                )
                log.debug(
                    "polling_consumer.empty_poll",
                    consecutive=consecutive_empty,
                    sleep_s=sleep,
                )
                await asyncio.sleep(sleep)
                continue

            consecutive_empty = 0
            any_claimed = False

            for decision_id in ids:
                if not self._running:
                    break

                try:
                    decision = await self._repo.claim_for_execution(
                        decision_id=decision_id,
                        worker_id=settings.worker_id,
                    )
                except Exception as exc:
                    log.error(
                        "polling_consumer.claim_error",
                        decision_id=decision_id,
                        error=str(exc),
                    )
                    continue

                if decision is None:
                    # Race — another worker claimed this one.
                    continue

                any_claimed = True
                log.info(
                    "polling_consumer.claimed",
                    decision_id=decision_id,
                    symbol=decision.symbol,
                    mode=decision.mode,
                    final_decision=decision.final_decision,
                )
                yield decision

                # Brief pause between claims to distribute work across replicas
                await asyncio.sleep(0.05)

            if not any_claimed:
                await asyncio.sleep(1.0)
