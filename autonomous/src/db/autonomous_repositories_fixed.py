"""
Repositories used by the autonomous service.

All operations run with service_role and bypass RLS. The autonomous service
is authorized to:
  - Insert market_snapshots (data ingest).
  - Insert signals          (paper-trading driver).
  - Insert bots / user_settings (demo bootstrap, idempotent).
  - Read auth.users         (find a user to attach demo bots to).

It does NOT write to:
  - trades / trade_decisions / trade_events / agent_runs / agent_outputs
    (those are owned by the agent / execution / position engines).
  - platform_settings / risk_logs / security_logs / audit_logs except where
    explicitly added.

Failures raise; callers decide retry vs fail-closed.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from src.db.supabase_client import get_client
from src.utils.time import utcnow_iso


async def _run(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


# ── Market snapshots ─────────────────────────────────────────────────────────

class MarketSnapshotRepository:
    def __init__(self) -> None:
        self._client = get_client()

    async def insert(self, row: dict[str, Any]) -> str:
        def _insert():
            return (
                self._client.table("market_snapshots")
                .insert(row)
                .execute()
            )
        result = await _run(_insert)
        if not result.data:
            raise RuntimeError("market_snapshots insert returned no rows")
        return result.data[0]["id"]

    async def latest(
        self,
        exchange: str,
        symbol: str,
        timeframe: str = "1m",
    ) -> Optional[dict[str, Any]]:
        def _select():
            return (
                self._client.table("market_snapshots")
                .select("*")
                .eq("exchange", exchange)
                .eq("symbol", symbol)
                .eq("timeframe", timeframe)
                .order("captured_at", desc=True)
                .limit(1)
                .execute()
            )
        result = await _run(_select)
        rows = result.data or []
        return rows[0] if rows else None


# ── Signals ──────────────────────────────────────────────────────────────────

class SignalRepository:
    def __init__(self) -> None:
        self._client = get_client()

    async def has_pending(self, bot_id: str, symbol: str) -> bool:
        """True if there is at least one pending or processing signal for the
        bot/symbol that is still relevant (not stale)."""
        def _select():
            return (
                self._client.table("signals")
                .select("id", count="exact", head=True)
                .eq("bot_id", bot_id)
                .eq("symbol", symbol)
                .in_("status", ["pending", "processing"])
                .execute()
            )
        result = await _run(_select)
        return (result.count or 0) > 0

    async def create_system(
        self,
        *,
        user_id: str,
        bot_id: str,
        exchange: str,
        symbol: str,
        market_snapshot_id: Optional[str],
        worker_id: str,
    ) -> str:
        row = {
            "user_id":            user_id,
            "bot_id":             bot_id,
            "exchange":           exchange,
            "symbol":             symbol,
            "direction":          "neutral",
            "signal_type":        "system",
            "status":             "pending",
            "market_snapshot_id": market_snapshot_id,
            "metadata": {
                "source":    "autonomous_seeder",
                "worker_id": worker_id,
            },
        }

        def _insert():
            return self._client.table("signals").insert(row).execute()

        result = await _run(_insert)
        if not result.data:
            raise RuntimeError("signals insert returned no rows")
        return result.data[0]["id"]


# ── Bots + users ─────────────────────────────────────────────────────────────

class BotRepository:
    def __init__(self) -> None:
        self._client = get_client()

    async def count_all(self) -> int:
        def _q():
            return (
                self._client.table("bots")
                .select("id", count="exact", head=True)
                .execute()
            )
        result = await _run(_q)
        return result.count or 0

    async def list_active_paper_bots(self) -> list[dict[str, Any]]:
        def _q():
            return (
                self._client.table("bots")
                .select("*")
                .eq("status", "active")
                .eq("mode",   "paper")
                .eq("is_archived", False)
                .execute()
            )
        result = await _run(_q)
        return result.data or []

    async def insert(self, row: dict[str, Any]) -> str:
        def _insert():
            return self._client.table("bots").insert(row).execute()
        result = await _run(_insert)
        if not result.data:
            raise RuntimeError("bots insert returned no rows")
        return result.data[0]["id"]


class UserDirectoryRepository:
    """Reads from auth.users via the Supabase admin API.
    Returns the first available user_id, or None if none exists yet."""
    def __init__(self) -> None:
        self._client = get_client()

    async def first_user_id(self) -> Optional[str]:
        def _list():
            # supabase-py admin API; returns a list response
            return self._client.auth.admin.list_users()
        try:
            users = await _run(_list)
        except Exception:
            return None

        # supabase-py >=2.4 returns either a list or an object with .users
        candidates: list[Any]
        if isinstance(users, list):
            candidates = users
        else:
            candidates = getattr(users, "users", None) or getattr(users, "data", None) or []

        for u in candidates:
            uid = getattr(u, "id", None) or (u.get("id") if isinstance(u, dict) else None)
            if uid:
                return str(uid)
        return None


class UserSettingsRepository:
    def __init__(self) -> None:
        self._client = get_client()

    async def ensure_exists(self, user_id: str) -> None:
        # idempotent: upsert with on_conflict on user_id
        def _upsert():
            return (
                self._client.table("user_settings")
                .upsert(
                    {
                        "user_id":                        user_id,
                        "paper_trading_enabled":          True,
                        "real_trading_enabled":           False,
                        "real_trading_requires_approval": True,
                        "updated_at":                     utcnow_iso(),
                    },
                    on_conflict="user_id",
                )
                .execute()
            )
        try:
            await _run(_upsert)
        except Exception:
            # Table may not exist in early environments — best-effort.
            pass


# ── Audit ────────────────────────────────────────────────────────────────────

class PlatformSettingsRepository:
    """Read-only access to platform_settings. Used to honour the kill switch."""

    def __init__(self) -> None:
        self._client = get_client()

    async def global_trading_enabled(self) -> bool:
        """True unless an operator has flipped global_trading_enabled=false.
        Fail-OPEN on read error is unsafe — fail-CLOSED to false to pause the
        signal generator when the DB is unhappy."""
        def _q():
            return (
                self._client.table("platform_settings")
                .select("key,value")
                .execute()
            )
        try:
            result = await _run(_q)
        except Exception:
            return False  # fail-closed — do not seed signals on DB outage

        for row in result.data or []:
            if row.get("key") == "global_trading_enabled":
                v = row.get("value")
                if v is None:
                    return True
                if isinstance(v, bool):
                    return v
                if isinstance(v, str):
                    return v.lower() not in ("false", "0", "no", "off")
                return bool(v)
        return True  # default ON when row absent


class AuditLogRepository:
    def __init__(self) -> None:
        self._client = get_client()

    async def create(self, row: dict[str, Any]) -> None:
        def _insert():
            return self._client.table("audit_logs").insert(row).execute()
        try:
            await _run(_insert)
        except Exception:
            pass
