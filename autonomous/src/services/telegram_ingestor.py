"""Telegram listener that turns whitelisted group messages into signals."""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from typing import Any

from src.config import settings
from src.db.repositories import SignalRepository, TelegramSignalRepository
from src.heartbeat import tracker
from src.logging_config import get_logger
from src.services.telegram_parser import parse_telegram_signal

log = get_logger(__name__)


class TelegramSignalIngestor:
    name = "telegram_ingestor"

    def __init__(self) -> None:
        tracker.register(self.name)
        self._sources = TelegramSignalRepository()
        self._signals = SignalRepository()

    async def run(self) -> None:
        if not settings.telegram_ingestion_enabled:
            tracker.beat(self.name, "disabled")
            log.info("telegram_ingestor.disabled")
            return

        if not settings.telegram_api_id or not settings.telegram_api_hash:
            tracker.beat(self.name, "missing_config")
            log.warning("telegram_ingestor.missing_api_config")
            return

        try:
            from telethon import TelegramClient, events
            from telethon.sessions import StringSession
        except ImportError:
            tracker.beat(self.name, "missing_dependency")
            log.error("telegram_ingestor.telethon_missing")
            return

        async def _run_client(session_string: str) -> None:
            client = TelegramClient(
                StringSession(session_string),
                settings.telegram_api_id,
                settings.telegram_api_hash,
            )

            @client.on(events.NewMessage)
            async def _on_message(event: Any) -> None:
                await self._handle_event(event)

            async with client:
                tracker.beat(self.name, "running")
                await client.run_until_disconnected()

        tasks: dict[str, asyncio.Task] = {}
        log.info("telegram_ingestor.starting")
        while True:
            session_strings: list[str] = []
            if settings.telegram_session_string:
                session_strings.append(settings.telegram_session_string)

            for account in await self._sources.list_connected_accounts():
                session = account.get("session_ciphertext")
                if session:
                    session_strings.append(str(session))

            for session in session_strings:
                key = session[-32:]
                if key not in tasks or tasks[key].done():
                    tasks[key] = asyncio.create_task(_run_client(session))

            for key, task in list(tasks.items()):
                if task.done():
                    tasks.pop(key, None)

            tracker.beat(self.name, "running" if tasks else "missing_session", sessions=len(tasks))
            await asyncio.sleep(settings.telegram_listener_reload_seconds)

    async def _handle_event(self, event: Any) -> None:
        text = (getattr(event, "raw_text", None) or "").strip()
        if not text:
            return

        chat_id = str(getattr(event, "chat_id", "") or "")
        if not chat_id:
            return

        topic_id = _event_topic_id(event)
        source = await self._sources.get_source_for_chat_topic(chat_id, topic_id)
        if not source:
            return

        telegram_message_id = str(getattr(event, "id", "") or "")
        if not telegram_message_id:
            return

        if await self._sources.message_exists(source["id"], telegram_message_id):
            return

        received_at = _event_datetime(event)
        parsed = parse_telegram_signal(text)
        normalized = _normalized_payload(parsed)
        status, error = _parse_status(source, normalized, parsed.confidence, parsed.warnings)

        message_row_id = await self._sources.record_message(
            source_id=source["id"],
            user_id=source["user_id"],
            telegram_message_id=telegram_message_id,
            raw_text=text,
            received_at=received_at,
            normalized_signal=normalized,
            parse_status=status,
            parse_error=error,
        )

        if status != "parsed":
            log.info(
                "telegram_signal.rejected",
                source_id=source["id"],
                chat_id=chat_id,
                message_id=telegram_message_id,
                reason=error,
            )
            return

        signal_id = await self._signals.create_telegram(
            user_id=source["user_id"],
            bot_id=source["bot_id"],
            exchange=source.get("exchange") or "binance",
            symbol=normalized["symbol"],
            direction=normalized["direction"],
            confidence=parsed.confidence,
            metadata={
                **parsed.to_metadata(),
                "telegram_source_id": source["id"],
                "telegram_message_row_id": message_row_id,
                "telegram_message_id": telegram_message_id,
                "telegram_chat_id": chat_id,
                "telegram_chat_title": source.get("chat_title"),
                "telegram_topic_id": topic_id,
                "telegram_topic_title": source.get("topic_title"),
                "execution_policy": source.get("execution_policy"),
            },
        )
        await self._sources.mark_signal_created(message_row_id, signal_id)
        tracker.beat(self.name, "ok", last_signal_id=signal_id)
        log.info(
            "telegram_signal.created",
            signal_id=signal_id,
            source_id=source["id"],
            symbol=normalized["symbol"],
            direction=normalized["direction"],
        )


def _event_datetime(event: Any) -> str:
    value = getattr(event, "date", None)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return datetime.now(timezone.utc).isoformat()


def _event_topic_id(event: Any) -> str | None:
    message = getattr(event, "message", None)
    reply_to = getattr(message, "reply_to", None)
    raw = (
        getattr(reply_to, "reply_to_top_id", None)
        or getattr(reply_to, "reply_to_msg_id", None)
        or getattr(message, "reply_to_top_id", None)
    )
    return str(raw) if raw else None


def _normalized_payload(parsed: Any) -> dict[str, Any]:
    return {
        "symbol": parsed.symbol,
        "direction": parsed.direction,
        "entry_min": parsed.entry_min,
        "entry_max": parsed.entry_max,
        "entry_price": parsed.entry_price,
        "take_profits": parsed.take_profits,
        "stop_loss": parsed.stop_loss,
        "leverage": parsed.leverage,
        "confidence": parsed.confidence,
        "warnings": parsed.warnings,
    }


def _parse_status(
    source: dict[str, Any],
    normalized: dict[str, Any],
    confidence: float,
    warnings: list[str],
) -> tuple[str, str | None]:
    if not normalized.get("symbol"):
        return "ignored", "No tradable symbol found"
    if normalized.get("direction") not in {"long", "short"}:
        return "ignored", "No long/short direction found"
    if confidence < float(source.get("min_parse_confidence") or 0.7):
        return "rejected", "Parse confidence below source threshold"
    if source.get("require_stop_loss", True) and "missing_stop_loss" in warnings:
        return "rejected", "Stop-loss is required for this Telegram source"
    if any(str(w).startswith("invalid_") for w in warnings):
        return "rejected", ", ".join(warnings)

    allowlist = [str(s).upper() for s in (source.get("symbol_allowlist") or [])]
    symbol = str(normalized.get("symbol") or "").upper()
    if allowlist and symbol not in allowlist:
        return "ignored", f"{symbol} is not in this source allowlist"

    return "parsed", None
