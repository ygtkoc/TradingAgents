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
from datetime import datetime, timedelta, timezone
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

    async def count_recent(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        *,
        since_minutes: int = 300,
    ) -> int:
        """Count snapshots for (exchange, symbol, timeframe) in the last N minutes.

        Used before pre-seeding historical bars to avoid redundant inserts
        on frequent service restarts.
        """
        from datetime import datetime, timedelta, timezone
        cutoff = (
            datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
        ).isoformat()

        def _count():
            return (
                self._client.table("market_snapshots")
                .select("id", count="exact", head=True)
                .eq("exchange", exchange)
                .eq("symbol", symbol)
                .eq("timeframe", timeframe)
                .gte("captured_at", cutoff)
                .execute()
            )
        result = await _run(_count)
        return result.count or 0

    async def bulk_insert(self, rows: list[dict]) -> None:
        """Batch-insert historical snapshot rows.

        Uses a single INSERT so the round-trip cost is O(1) regardless of
        the number of rows. Errors are propagated to the caller.
        """
        if not rows:
            return

        def _insert():
            return (
                self._client.table("market_snapshots")
                .insert(rows)
                .execute()
            )
        await _run(_insert)

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

    async def list_recent_symbols(
        self,
        exchange: str,
        timeframe: str,
        *,
        since_minutes: int = 10,
    ) -> list[str]:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
        ).isoformat()

        def _select():
            return (
                self._client.table("market_snapshots")
                .select("symbol")
                .eq("exchange", exchange)
                .eq("timeframe", timeframe)
                .gte("captured_at", cutoff)
                .execute()
            )
        result = await _run(_select)
        rows = result.data or []
        return sorted({
            str(row.get("symbol")).upper()
            for row in rows
            if row.get("symbol")
        })


# ── Signals ──────────────────────────────────────────────────────────────────

class SignalRepository:
    def __init__(self) -> None:
        self._client = get_client()

    async def count_inflight(
        self,
        bot_id: str,
        symbol: str,
        *,
        max_age_minutes: int,
    ) -> int:
        """Count recent pending/processing signals for the bot/symbol."""
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)).isoformat()

        def _select():
            return (
                self._client.table("signals")
                .select("id", count="exact", head=True)
                .eq("bot_id", bot_id)
                .eq("symbol", symbol)
                .in_("status", ["pending", "processing"])
                .gte("created_at", cutoff)
                .execute()
            )
        result = await _run(_select)
        return result.count or 0

    async def has_pending(self, bot_id: str, symbol: str, *, max_age_minutes: int) -> bool:
        """True if there is at least one recent pending or processing signal."""
        return (await self.count_inflight(
            bot_id,
            symbol,
            max_age_minutes=max_age_minutes,
        )) > 0

    async def last_completed_at(
        self,
        bot_id: str,
        symbol: str,
    ) -> Optional[datetime]:
        """Return the created_at of the most recent *completed* signal for this
        bot+symbol (excludes pending/processing rows).

        Returns None when no completed signal exists, signalling that no
        cooldown has elapsed yet (seed immediately).
        """
        def _select():
            return (
                self._client.table("signals")
                .select("created_at")
                .eq("bot_id", bot_id)
                .eq("symbol", symbol)
                .not_.in_("status", ["pending", "processing"])
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
        result = await _run(_select)
        rows = result.data or []
        if not rows:
            return None
        ts = rows[0].get("created_at")
        if not ts:
            return None
        if isinstance(ts, datetime):
            return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts
        try:
            return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None

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

    async def list_unique_trading_pairs(self) -> list[str]:
        """Return all distinct trading_pairs symbols across active paper bots.

        Used by the market-data feed to build a dynamic WS subscription that
        covers whatever the user has configured — including user-created bots
        with non-default symbols like DOGE/USDT or ARB/USDT.
        """
        bots = await self.list_active_paper_bots()
        seen: set[str] = set()
        for bot in bots:
            pairs = bot.get("trading_pairs") or []
            if isinstance(pairs, list):
                for p in pairs:
                    if p and isinstance(p, str):
                        seen.add(p.upper())
        return sorted(seen)

    async def insert(self, row: dict[str, Any]) -> str:
        def _insert():
            return self._client.table("bots").insert(row).execute()
        result = await _run(_insert)
        if not result.data:
            raise RuntimeError("bots insert returned no rows")
        return result.data[0]["id"]

    async def update_warmup_status(
        self,
        bot_id: str,
        warmup_status: str,
        candles_collected: int,
        *,
        warmup_started_at: Optional[datetime] = None,
        warmup_completed_at: Optional[datetime] = None,
    ) -> None:
        """Persist warmup state changes to the bots table."""
        payload: dict[str, Any] = {
            "warmup_status":     warmup_status,
            "candles_collected": candles_collected,
        }
        if warmup_started_at is not None:
            payload["warmup_started_at"] = warmup_started_at.isoformat()
        if warmup_completed_at is not None:
            payload["warmup_completed_at"] = warmup_completed_at.isoformat()

        def _update():
            return (
                self._client.table("bots")
                .update(payload)
                .eq("id", bot_id)
                .execute()
            )
        await _run(_update)

    async def update_signal_timestamps(
        self,
        bot_id: str,
        last_signal_at: datetime,
        next_signal_at: datetime,
    ) -> None:
        """Persist last_signal_at / next_signal_at after a signal is seeded."""
        def _update():
            return (
                self._client.table("bots")
                .update({
                    "last_signal_at": last_signal_at.isoformat(),
                    "next_signal_at": next_signal_at.isoformat(),
                })
                .eq("id", bot_id)
                .execute()
            )
        await _run(_update)


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

class PaperAccountStatusRepository:
    """Read paper_accounts.status to honour per-user start/pause control.

    Signal generator consults this every tick. Caches in-memory for 10s to
    avoid hitting the DB once per (bot, symbol) pair within a tick burst.
    """

    _CACHE_TTL_SECONDS = 10.0

    def __init__(self) -> None:
        self._client = get_client()
        self._cache:    dict[str, tuple[float, str]] = {}   # user_id → (cached_at_monotonic, status)

    async def status(self, user_id: str) -> str:
        """Returns 'active' | 'paused' | 'inactive' | 'missing'."""
        import time
        now = time.monotonic()
        hit = self._cache.get(user_id)
        if hit and (now - hit[0]) < self._CACHE_TTL_SECONDS:
            return hit[1]

        def _q():
            return (
                self._client.table("paper_accounts")
                .select("status")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
        try:
            r = await _run(_q)
        except Exception:
            self._cache[user_id] = (now, "missing")
            return "missing"

        row = r.data if r and getattr(r, "data", None) else None
        status = (row or {}).get("status") or "missing"
        self._cache[user_id] = (now, status)
        return status

    async def ensure_active(self, user_id: str) -> str:
        """Force a paper account into active status for autonomous demo flow."""
        now_iso = utcnow_iso()

        def _update():
            return (
                self._client.table("paper_accounts")
                .update(
                    {
                        "status": "active",
                        "started_at": now_iso,
                        "paused_at": None,
                    }
                )
                .eq("user_id", user_id)
                .execute()
            )

        await _run(_update)
        status = await self.status(user_id)
        import time
        self._cache[user_id] = (time.monotonic(), status)
        return status

    def invalidate(self, user_id: str | None = None) -> None:
        if user_id is None:
            self._cache.clear()
        else:
            self._cache.pop(user_id, None)


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
