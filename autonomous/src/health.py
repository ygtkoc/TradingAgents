"""
Tiny aiohttp /health server. Exposes liveness for the autonomous service.

GET /health → 200 / 503
{
  "status":   "ok" | "degraded" | "unhealthy",
  "uptime_s": 123.4,
  "services": {
    "market_data":      {"service": "market_data",      "status": "ok",  ...},
    "signal_generator": {"service": "signal_generator", "status": "ok",  ...},
    "bootstrap":        {"service": "bootstrap",        "status": "ok",  ...},
    "heartbeat":        {"service": "heartbeat",        "status": "ok",  ...},
    "db":               {"service": "db",               "status": "ok",  ...}
  }
}
"""
from __future__ import annotations

import time

from aiohttp import web

from src.config import settings
from src.db.supabase_client import get_client
from src.db.repositories import TelegramSignalRepository
from src.heartbeat import tracker
from src.logging_config import get_logger

log = get_logger(__name__)


def _cors_headers() -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": settings.telegram_api_cors_origin,
        "Access-Control-Allow-Headers": "content-type, authorization",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    }


def _json(body: dict, *, status: int = 200) -> web.Response:
    return web.json_response(body, status=status, headers=_cors_headers())


async def _read_json(request: web.Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="Request body must be JSON", headers=_cors_headers())
    return body if isinstance(body, dict) else {}


def _aggregate_status(services: dict[str, dict]) -> str:
    if not services:
        return "unhealthy"
    statuses = [s.get("status") for s in services.values()]
    if any(s == "failed"                 for s in statuses):
        return "unhealthy"
    if any(s in ("error", "stale")       for s in statuses):
        return "degraded"
    if any(s == "starting" or s is None  for s in statuses):
        return "degraded"
    if any(s in ("paused", "degraded")   for s in statuses):
        return "degraded"
    return "ok"


async def _db_check() -> dict:
    """Tiny `select 1`-style probe so /health reflects DB availability."""
    try:
        # supabase-py is synchronous → run on default executor for speed.
        import asyncio
        def _q():
            # platform_settings always exists (migration 0002+) and is small.
            return get_client().table("platform_settings").select("key", count="exact", head=True).limit(1).execute()
        await asyncio.to_thread(_q)
        return {"service": "db", "status": "ok"}
    except Exception as exc:
        return {"service": "db", "status": "error", "error": str(exc)[:200]}


async def make_app(started_at: float) -> web.Application:
    async def health(_request: web.Request) -> web.Response:
        services = tracker.all()
        services["db"] = await _db_check()

        status = _aggregate_status(services)
        body   = {
            "status":   status,
            "uptime_s": round(time.monotonic() - started_at, 1),
            "worker":   settings.autonomous_worker_id,
            "services": services,
        }
        http_status = 200 if status == "ok" else 503 if status == "unhealthy" else 200
        return web.json_response(body, status=http_status)

    async def liveness(_req: web.Request) -> web.Response:
        return web.json_response({"alive": True})

    async def options(_request: web.Request) -> web.Response:
        return web.Response(status=204, headers=_cors_headers())

    async def telegram_auth_start(request: web.Request) -> web.Response:
        try:
            body = await _read_json(request)
            user_id = str(body.get("user_id") or "")
            phone = str(body.get("phone_number") or "")
            label = str(body.get("account_label") or "Telegram")
            if not user_id or not phone:
                return _json({"ok": False, "error": "user_id and phone_number are required"}, status=422)
            if not settings.telegram_api_id or not settings.telegram_api_hash:
                return _json({"ok": False, "error": "Telegram API config is missing"}, status=503)

            try:
                from telethon import TelegramClient
                from telethon.sessions import StringSession
            except ImportError:
                return _json({"ok": False, "error": "Telethon is not installed"}, status=503)

            repo = TelegramSignalRepository()
            client = TelegramClient(StringSession(), settings.telegram_api_id, settings.telegram_api_hash)
            await client.connect()
            try:
                sent = await client.send_code_request(phone)
                account_id = await repo.create_pending_account(
                    user_id=user_id,
                    account_label=label,
                    phone_hint=_phone_hint(phone),
                    pending_session=client.session.save(),
                    phone_code_hash=sent.phone_code_hash,
                )
                return _json({"ok": True, "account_id": account_id, "phone_hint": _phone_hint(phone)})
            finally:
                await client.disconnect()
        except Exception as exc:
            log.exception("telegram.auth_start.failed", error=str(exc)[:300])
            return _json({"ok": False, "error": str(exc)[:300]}, status=400)

    async def telegram_auth_verify(request: web.Request) -> web.Response:
        body = await _read_json(request)
        user_id = str(body.get("user_id") or "")
        account_id = str(body.get("account_id") or "")
        phone = str(body.get("phone_number") or "")
        code = str(body.get("code") or "")
        password = body.get("password")
        if not user_id or not account_id or not phone or not code:
            return _json({"ok": False, "error": "user_id, account_id, phone_number and code are required"}, status=422)

        try:
            from telethon import TelegramClient
            from telethon.errors import SessionPasswordNeededError
            from telethon.sessions import StringSession
        except ImportError:
            return _json({"ok": False, "error": "Telethon is not installed"}, status=503)

        repo = TelegramSignalRepository()
        account = await repo.get_account(user_id, account_id)
        if not account:
            return _json({"ok": False, "error": "Telegram account not found"}, status=404)

        client = TelegramClient(
            StringSession(account.get("session_ciphertext") or ""),
            settings.telegram_api_id,
            settings.telegram_api_hash,
        )
        await client.connect()
        try:
            try:
                await client.sign_in(
                    phone=phone,
                    code=code,
                    phone_code_hash=(account.get("metadata") or {}).get("phone_code_hash"),
                )
            except SessionPasswordNeededError:
                if not password:
                    return _json({"ok": False, "requires_password": True})
                await client.sign_in(password=str(password))

            session_string = client.session.save()
            await repo.mark_account_connected(account_id, session_string)
            return _json({"ok": True, "account_id": account_id})
        except Exception as exc:
            await repo.mark_account_error(account_id, str(exc))
            return _json({"ok": False, "error": str(exc)[:300]}, status=400)
        finally:
            await client.disconnect()

    async def telegram_chats(request: web.Request) -> web.Response:
        body = await _read_json(request)
        user_id = str(body.get("user_id") or "")
        account_id = str(body.get("account_id") or "")
        if not user_id or not account_id:
            return _json({"ok": False, "error": "user_id and account_id are required"}, status=422)

        try:
            from telethon import TelegramClient
            from telethon.sessions import StringSession
        except ImportError:
            return _json({"ok": False, "error": "Telethon is not installed"}, status=503)

        repo = TelegramSignalRepository()
        account = await repo.get_account(user_id, account_id)
        if not account or account.get("connection_status") != "connected":
            return _json({"ok": False, "error": "Connected Telegram account not found"}, status=404)

        client = TelegramClient(
            StringSession(account.get("session_ciphertext") or ""),
            settings.telegram_api_id,
            settings.telegram_api_hash,
        )
        await client.connect()
        try:
            rows = []
            response = []
            async for dialog in client.iter_dialogs():
                entity = dialog.entity
                is_groupish = bool(getattr(dialog, "is_group", False) or getattr(dialog, "is_channel", False))
                if not is_groupish:
                    continue
                chat_id = str(dialog.id)
                title = dialog.name or chat_id
                has_topics = bool(getattr(entity, "forum", False))
                topics = await _telegram_topics(client, entity) if has_topics else []
                item = {
                    "chat_id": chat_id,
                    "chat_title": title,
                    "chat_type": "channel" if getattr(dialog, "is_channel", False) else "group",
                    "has_topics": has_topics,
                    "topics": topics,
                }
                response.append(item)
                rows.append({
                    "user_id": user_id,
                    "telegram_account_id": account_id,
                    "chat_id": chat_id,
                    "chat_title": title,
                    "chat_type": item["chat_type"],
                    "has_topics": has_topics,
                    "topic_id": None,
                    "topic_title": None,
                    "metadata": {},
                })
                for topic in topics:
                    rows.append({
                        "user_id": user_id,
                        "telegram_account_id": account_id,
                        "chat_id": chat_id,
                        "chat_title": title,
                        "chat_type": item["chat_type"],
                        "has_topics": True,
                        "topic_id": topic["topic_id"],
                        "topic_title": topic["topic_title"],
                        "metadata": {},
                    })

            await repo.replace_chat_options(
                user_id=user_id,
                telegram_account_id=account_id,
                rows=rows,
            )
            return _json({"ok": True, "chats": response})
        finally:
            await client.disconnect()

    app = web.Application()
    app.router.add_get("/health",  health)
    app.router.add_get("/healthz", health)
    app.router.add_get("/live",    liveness)
    app.router.add_route("OPTIONS", "/telegram/{tail:.*}", options)
    app.router.add_post("/telegram/auth/start", telegram_auth_start)
    app.router.add_post("/telegram/auth/verify", telegram_auth_verify)
    app.router.add_post("/telegram/chats", telegram_chats)
    return app


async def start_health_server(started_at: float) -> web.AppRunner:
    """Returns the AppRunner so caller can await runner.cleanup() on shutdown."""
    app    = await make_app(started_at)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site   = web.TCPSite(runner, "0.0.0.0", settings.health_port)
    await site.start()
    log.info("health.listening", port=settings.health_port, path="/health")
    return runner


def _phone_hint(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    return f"***{digits[-4:]}" if len(digits) >= 4 else "***"


async def _telegram_topics(client, entity) -> list[dict[str, str]]:
    try:
        from telethon import functions

        result = await client(
            functions.channels.GetForumTopicsRequest(
                channel=entity,
                q="",
                offset_date=None,
                offset_id=0,
                offset_topic=0,
                limit=100,
            )
        )
        topics = []
        for topic in getattr(result, "topics", []) or []:
            topic_id = getattr(topic, "id", None)
            title = getattr(topic, "title", None)
            if topic_id is not None and title:
                topics.append({"topic_id": str(topic_id), "topic_title": str(title)})
        return topics
    except Exception:
        return []
