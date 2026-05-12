"""
PGMQ queue consumer (optional — higher throughput alternative to polling).

PGMQ is a Postgres-native message queue extension. If the pgmq extension
is installed in Supabase, this consumer uses it for lower-latency signal
delivery and built-in visibility timeout / dead-letter queue semantics.

Falls back to PollingConsumer if the pgmq extension is not available.

Queue name convention: "trading_signals_{exchange}_{symbol}" or
                       "trading_signals_all" for a catch-all queue.

Note: This implementation requires the pgmq extension:
  CREATE EXTENSION IF NOT EXISTS pgmq;
  SELECT pgmq.create('trading_signals_all');
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator, Optional

from src.config import settings
from src.db.models import Signal
from src.logging_config import get_logger
from src.queue.base import BaseQueueConsumer
from src.queue.polling import PollingConsumer

log = get_logger(__name__)

_PGMQ_QUEUE_NAME = "trading_signals_all"
_VISIBILITY_TIMEOUT_SECONDS = 120  # Must be > pipeline_timeout_seconds


class PgmqConsumer(BaseQueueConsumer):
    """
    PGMQ-backed consumer. Uses pgmq.read() to dequeue with visibility timeout.
    If PGMQ is unavailable, delegates entirely to PollingConsumer.

    Message format expected in queue:
    {
        "signal_id": "<uuid>",
        "symbol": "BTC/USDT",
        "exchange": "binance"
    }
    The consumer fetches the full signal from the DB by id.
    """

    def __init__(self) -> None:
        self._available: Optional[bool] = None
        self._fallback: Optional[PollingConsumer] = None
        self._msg_ids: dict[str, int] = {}  # signal_id -> pgmq msg_id for ack
        from src.db.repositories import SignalRepository
        self._signal_repo = SignalRepository()

    async def _check_pgmq_available(self) -> bool:
        """Returns True if pgmq extension is installed and queue exists."""
        try:
            import asyncio as _asyncio
            from src.db.supabase_client import get_client
            client = get_client()

            # Check if pgmq functions exist
            result = await _asyncio.to_thread(
                lambda: client.rpc("pgmq_version", {}).execute()
            )
            return True
        except Exception:
            return False

    async def __aenter__(self) -> "PgmqConsumer":
        self._available = await self._check_pgmq_available()
        if not self._available:
            log.warning(
                "pgmq_consumer.unavailable",
                message="PGMQ extension not found — falling back to polling consumer",
            )
            self._fallback = PollingConsumer()
            await self._fallback.__aenter__()
        else:
            log.info("pgmq_consumer.started", queue=_PGMQ_QUEUE_NAME)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._fallback:
            await self._fallback.__aexit__(exc_type, exc_val, exc_tb)
        else:
            log.info("pgmq_consumer.stopped")

    def stop(self) -> None:
        if self._fallback:
            self._fallback.stop()

    async def consume(self) -> AsyncIterator[Signal]:
        if self._fallback:
            async for signal in self._fallback.consume():
                yield signal
            return

        # PGMQ path
        from src.db.supabase_client import get_client
        import asyncio

        client = get_client()

        while True:
            try:
                # pgmq.read(queue_name, visibility_timeout, batch_size)
                result = await asyncio.to_thread(
                    lambda: client.rpc(
                        "pgmq_read",
                        {
                            "queue_name": _PGMQ_QUEUE_NAME,
                            "vt": _VISIBILITY_TIMEOUT_SECONDS,
                            "qty": 1,
                        },
                    ).execute()
                )
                messages = result.data or []
                if not messages:
                    await asyncio.sleep(settings.poll_interval_seconds)
                    continue

                msg = messages[0]
                msg_id = msg["msg_id"]
                payload = msg["message"]

                if isinstance(payload, str):
                    payload = json.loads(payload)

                signal_id = payload.get("signal_id")
                if not signal_id:
                    log.error("pgmq_consumer.missing_signal_id", msg_id=msg_id)
                    await self._delete_message(client, msg_id)
                    continue

                signal = await self._signal_repo.get_by_id(signal_id)
                if signal is None:
                    log.error("pgmq_consumer.signal_not_found", signal_id=signal_id)
                    await self._delete_message(client, msg_id)
                    continue

                self._msg_ids[signal_id] = msg_id
                log.info(
                    "pgmq_consumer.dequeued",
                    signal_id=signal_id,
                    msg_id=msg_id,
                )
                yield signal

            except Exception as exc:
                log.error("pgmq_consumer.error", error=str(exc))
                await asyncio.sleep(settings.poll_interval_seconds)

    async def ack(self, signal: Signal) -> None:
        signal_id = str(signal.id)
        if self._fallback:
            await self._fallback.ack(signal)
            return

        msg_id = self._msg_ids.pop(signal_id, None)
        if msg_id is None:
            log.warning("pgmq_consumer.ack_no_msg_id", signal_id=signal_id)
            return

        from src.db.supabase_client import get_client
        import asyncio
        client = get_client()
        await self._delete_message(client, msg_id)
        await self._signal_repo.mark_processed(signal_id)

    async def nack(self, signal: Signal, reason: str) -> None:
        if self._fallback:
            await self._fallback.nack(signal, reason)
            return

        signal_id = str(signal.id)
        # Don't delete — let visibility timeout expire so it re-queues
        self._msg_ids.pop(signal_id, None)
        await self._signal_repo.mark_failed(signal_id, reason)

    async def _delete_message(self, client, msg_id: int) -> None:
        import asyncio
        try:
            await asyncio.to_thread(
                lambda: client.rpc(
                    "pgmq_delete",
                    {"queue_name": _PGMQ_QUEUE_NAME, "msg_id": msg_id},
                ).execute()
            )
        except Exception as exc:
            log.error("pgmq_consumer.delete_error", msg_id=msg_id, error=str(exc))
