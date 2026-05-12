"""
DB polling queue consumer — two-phase atomic signal claiming.

Phase 1 — fetch_pending_ids(): SELECT ids of unclaimed pending signals.
           Non-locking. Multiple workers can call this concurrently.
Phase 2 — claim_by_id(): UPDATE WHERE id=X AND status='pending' RETURNING *.
           Atomic. If 0 rows → another worker claimed it → skip silently.

This fully prevents duplicate processing across worker replicas.
No signal is ever processed by more than one worker.

On transient failure:
  Leave signal in 'processing'. The release_stuck_signals() DB function
  (pg_cron, every 5 min) resets stuck signals to 'pending' with retry_count++.
  This enforces a minimum 5-minute retry gap, preventing retry storms.

On permanent failure:
  Call consumer.nack_permanent() → status='failed', never retried.
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

from src.config import settings
from src.db.models import Signal
from src.db.repositories import SignalRepository
from src.logging_config import get_logger
from src.queue.base import BaseQueueConsumer

log = get_logger(__name__)

_FETCH_BATCH = 5   # IDs to fetch per poll cycle (shared among concurrent workers)


class PollingConsumer(BaseQueueConsumer):
    """
    Two-phase polling consumer.

    Phase 1: fetch_pending_ids() — get a small batch of candidate IDs.
    Phase 2: claim_by_id() — atomically claim each one. Skip if already claimed.

    The generator yields only successfully claimed signals. The caller
    (main.py _process_signal) must call ack() on success or nack_permanent()
    on non-retryable failures. Transient failures (timeouts, pipeline errors)
    need no explicit call — release_stuck_signals() handles them server-side.
    """

    def __init__(self) -> None:
        self._repo = SignalRepository()
        self._running = False

    async def __aenter__(self) -> "PollingConsumer":
        self._running = True
        log.info("polling_consumer.started", interval_s=settings.poll_interval_seconds)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self._running = False
        log.info("polling_consumer.stopped")

    def stop(self) -> None:
        """Signal the consumer to stop after the current iteration."""
        self._running = False

    async def consume(self) -> AsyncIterator[Signal]:
        """
        Async generator — yields claimed Signal instances.

        Polls at `poll_interval_seconds`. Backs off exponentially on empty polls.
        Exits when self._running is False.
        """
        consecutive_empty = 0

        while self._running:
            try:
                ids = await self._repo.fetch_pending_ids(limit=_FETCH_BATCH)
            except Exception as exc:
                log.error("polling_consumer.fetch_error", error=str(exc))
                await asyncio.sleep(settings.poll_interval_seconds)
                continue

            if not ids:
                consecutive_empty += 1
                # Exponential back-off capped at 60 s to reduce DB load on quiet queues
                sleep = min(settings.poll_interval_seconds * min(consecutive_empty, 6), 60)
                log.debug("polling_consumer.empty_poll", consecutive=consecutive_empty, sleep_s=sleep)
                await asyncio.sleep(sleep)
                continue

            consecutive_empty = 0
            any_claimed = False

            for signal_id in ids:
                if not self._running:
                    break

                try:
                    signal = await self._repo.claim_by_id(
                        signal_id=signal_id,
                        worker_id=settings.worker_id,
                    )
                except Exception as exc:
                    log.error(
                        "polling_consumer.claim_error",
                        signal_id=signal_id,
                        error=str(exc),
                    )
                    continue

                if signal is None:
                    # Race — another worker claimed this one. Move to next.
                    continue

                any_claimed = True
                log.info(
                    "polling_consumer.claimed",
                    signal_id=signal_id,
                    symbol=signal.symbol,
                    exchange=signal.exchange,
                    direction=signal.direction.value,
                )
                yield signal

                # Brief pause between claims to share work across replicas
                await asyncio.sleep(0.05)

            if not any_claimed:
                # All IDs in this batch were claimed by other workers — short sleep
                await asyncio.sleep(1.0)

    async def ack(self, signal: Signal) -> None:
        """Mark signal as successfully processed."""
        try:
            await self._repo.mark_processed(str(signal.id))
            log.info("polling_consumer.ack", signal_id=str(signal.id))
        except Exception as exc:
            log.error("polling_consumer.ack_error", signal_id=str(signal.id), error=str(exc))

    async def nack_permanent(self, signal: Signal, reason: str) -> None:
        """
        Mark signal as permanently failed — will NOT be retried.

        Use for:
        - Invalid signal format / security rejection
        - Injection detected in metadata
        - Bot/user account permanently disabled
        - Signal schema validation failures

        Do NOT use for transient errors (network, DB timeouts, pipeline crashes).
        Those are left as 'processing' and reset by release_stuck_signals().
        """
        try:
            await self._repo.mark_permanently_failed(str(signal.id), reason)
            log.warning(
                "polling_consumer.nack_permanent",
                signal_id=str(signal.id),
                reason=reason[:200],
            )
        except Exception as exc:
            log.error(
                "polling_consumer.nack_error",
                signal_id=str(signal.id),
                error=str(exc),
            )

    async def nack(self, signal: Signal, reason: str) -> None:
        """
        Backwards-compatible alias for nack_permanent().
        Prefer nack_permanent() for explicit intent.
        """
        await self.nack_permanent(signal, reason)
