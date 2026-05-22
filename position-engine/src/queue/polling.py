"""
PollingTradePoller — fetches open trades from the DB on a fixed interval.

Two-phase atomic claim:
  Phase 1: fetch_claimable_ids()  — SELECT trade IDs (non-locking)
  Phase 2: claim_for_lifecycle()  — UPDATE WHERE lifecycle_status IN ('idle','needs_reconciliation')
                                    RETURNING *. Returns None if race lost.

Multiple workers can run this loop concurrently; the Phase 2 UPDATE is the
serialisation point — only one worker claims each trade per cycle.
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

from src.config import settings
from src.db.models import Trade
from src.db.repositories import TradeLifecycleRepository
from src.logging_config import get_logger
from src.queue.base import TradePoller

log = get_logger(__name__)


class PollingTradePoller(TradePoller):
    """
    Polls the trades table for claimable open trades on a fixed interval.

    Claims each trade atomically before yielding.
    Skips trades that were claimed by another worker between Phase 1 and Phase 2.
    """

    def __init__(self) -> None:
        self._repo    = TradeLifecycleRepository()
        self._stopped = False

    async def __aenter__(self) -> "PollingTradePoller":
        log.info(
            "poller.start",
            interval=settings.position_poll_interval_seconds,
            batch=settings.fetch_batch_size,
            worker=settings.worker_id,
        )
        return self

    async def __aexit__(self, *args) -> None:
        self._stopped = True
        log.info("poller.stop", worker=settings.worker_id)

    async def poll(self) -> AsyncIterator[Trade]:
        """
        Yield atomically-claimed Trade objects indefinitely.

        Sleeps between each full batch scan to avoid hammering the DB.
        """
        while not self._stopped:
            try:
                claimed_count = 0
                await self._repo.release_stale_claims(settings.position_stale_minutes)
                await self._repo.recover_transient_failures()

                # ── Phase 1: Fetch candidate IDs (non-locking) ───────────────
                ids = await self._repo.fetch_claimable_ids(
                    limit=settings.fetch_batch_size
                )

                if not ids:
                    log.debug(
                        "poller.no_claimable_trades",
                        worker=settings.worker_id,
                    )
                    await asyncio.sleep(settings.position_poll_interval_seconds)
                    continue

                log.debug(
                    "poller.candidates_found",
                    count=len(ids),
                    worker=settings.worker_id,
                )

                # ── Phase 2: Atomically claim each trade ─────────────────────
                for trade_id in ids:
                    if self._stopped:
                        return

                    trade = await self._repo.claim_for_lifecycle(
                        trade_id=trade_id,
                        worker_id=settings.worker_id,
                    )

                    if trade is None:
                        # Race lost — another worker claimed it
                        log.debug(
                            "poller.claim_race_lost",
                            trade_id=trade_id,
                        )
                        continue

                    claimed_count += 1
                    yield trade

                log.info(
                    "poller.batch_complete",
                    candidates=len(ids),
                    claimed=claimed_count,
                    worker=settings.worker_id,
                )

            except Exception as exc:
                log.error(
                    "poller.poll_error",
                    error=str(exc)[:300],
                    exc_info=True,
                )

            if not self._stopped:
                await asyncio.sleep(settings.position_poll_interval_seconds)
