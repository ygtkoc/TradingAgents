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
from src.heartbeat import tracker
from src.logging_config import get_logger

log = get_logger(__name__)


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

    app = web.Application()
    app.router.add_get("/health",  health)
    app.router.add_get("/healthz", health)
    app.router.add_get("/live",    liveness)
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
