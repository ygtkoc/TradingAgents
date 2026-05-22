"""
PaperAccountService (execution-side) — pre-check + reserve for paper opens.

Responsibilities here are intentionally small:

  reserve_for_open(user_id, trade_id, notional, …):
    • Looks up the user's paper_accounts row (RLS is bypassed by service_role).
    • Returns False if balance < notional → caller fails-closed and aborts the
      paper trade. NO trade row is created.
    • Otherwise debits the balance, inserts a paper_account_events row, and
      returns True. The DB CHECK constraint `balance >= 0` is the safety net
      against concurrent debits leaking a negative balance.

Close-side settlement lives in position-engine/src/services/paper_account.py.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from src.db.supabase_client import get_client
from src.logging_config import get_logger

log = get_logger(__name__)


async def _run(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


class InsufficientPaperBalance(Exception):
    """Raised when the paper account cannot cover an open. Caller must
    abort the trade — fail-closed."""


class PaperAccountService:
    def __init__(self) -> None:
        self._client = get_client()

    async def get_account(self, user_id: str) -> Optional[dict[str, Any]]:
        def _q():
            return (
                self._client.table("paper_accounts")
                .select("*")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
        try:
            r = await _run(_q)
        except Exception as exc:
            log.error("paper_account.read_failed", user_id=user_id, error=str(exc)[:200])
            return None
        return r.data if r and getattr(r, "data", None) else None

    async def reserve_for_open(
        self,
        *,
        user_id: str,
        trade_id: Optional[str],
        notional: float,
        symbol: str,
        reservation_id: Optional[str] = None,
    ) -> bool:
        """Debit paper_accounts.balance by the requested paper risk reserve and write a ledger
        event. Returns False if balance would go negative.

        DB CHECK constraint `balance >= 0` makes the underlying UPDATE fail
        on race conditions so concurrent opens cannot collectively over-spend.
        """
        if notional <= 0:
            log.warning("paper_account.reserve_skipped_nonpositive",
                        trade_id=trade_id, notional=notional)
            return True

        acct = await self.get_account(user_id)
        if acct is None:
            log.error("paper_account.no_account", user_id=user_id, trade_id=trade_id)
            return False

        balance = float(acct.get("balance") or 0)
        if balance < notional:
            log.warning(
                "paper_account.insufficient_balance",
                user_id=user_id, trade_id=trade_id, balance=balance, notional=notional,
            )
            return False

        new_balance = balance - notional

        # 1. Debit balance (constraint protects us on concurrent races).
        def _update():
            return (
                self._client.table("paper_accounts")
                .update({"balance": new_balance})
                .eq("id", acct["id"])
                .eq("user_id", user_id)
                .execute()
            )
        try:
            r = await _run(_update)
        except Exception as exc:
            # Likely the CHECK constraint or a stale-balance race. Fail-closed.
            log.warning("paper_account.debit_failed",
                        user_id=user_id, trade_id=trade_id, error=str(exc)[:200])
            return False
        if not (r.data or []):
            return False

        # 2. Append ledger event (best-effort; balance change is already booked).
        try:
            def _evt():
                return (
                    self._client.table("paper_account_events").insert({
                        "account_id":       acct["id"],
                        "user_id":          user_id,
                        "trade_id":         trade_id,
                        "event_type":       "trade_open_reserve",
                        "delta":            -notional,
                        "realized_delta":   0,
                        "unrealized_delta": 0,
                        "balance_after":    new_balance,
                        "realized_after":   acct.get("realized_pnl") or 0,
                        "unrealized_after": acct.get("unrealized_pnl") or 0,
                        "note":             f"open {symbol}",
                        "metadata":         {
                            "symbol": symbol,
                            "reserve_amount": notional,
                            "reserve_type": "risk_amount",
                            "reservation_id": reservation_id,
                            "trade_pending": trade_id is None,
                        },
                    }).execute()
                )
            await _run(_evt)
        except Exception as exc:
            log.error("paper_account.event_insert_failed",
                      user_id=user_id, trade_id=trade_id, error=str(exc)[:200])

        log.info("paper_account.reserved",
                 user_id=user_id, trade_id=trade_id, notional=notional,
                 balance_after=new_balance)
        return True

    async def attach_open_reservation(
        self,
        *,
        user_id: str,
        trade_id: str,
        reservation_id: str,
    ) -> None:
        """Best-effort: attach the pre-trade reserve ledger row to its trade."""
        if not reservation_id:
            return
        try:
            def _update():
                return (
                    self._client.table("paper_account_events")
                    .update({"trade_id": trade_id})
                    .eq("user_id", user_id)
                    .eq("event_type", "trade_open_reserve")
                    .is_("trade_id", "null")
                    .contains("metadata", {"reservation_id": reservation_id})
                    .execute()
                )
            await _run(_update)
        except Exception as exc:
            log.error(
                "paper_account.attach_reservation_failed",
                user_id=user_id, trade_id=trade_id, error=str(exc)[:200],
            )

    async def release_open_reservation(
        self,
        *,
        user_id: str,
        reservation_id: str,
        symbol: str,
        reason: str,
    ) -> None:
        """Best-effort rollback for a reserve made before trade creation."""
        if not reservation_id:
            return
        try:
            acct = await self.get_account(user_id)
            if acct is None:
                return

            def _events():
                return (
                    self._client.table("paper_account_events")
                    .select("*")
                    .eq("user_id", user_id)
                    .eq("event_type", "trade_open_reserve")
                    .is_("trade_id", "null")
                    .contains("metadata", {"reservation_id": reservation_id})
                    .limit(1)
                    .execute()
                )

            rows = (await _run(_events)).data or []
            if not rows:
                return

            event = rows[0]
            amount = abs(float(event.get("delta") or 0))
            if amount <= 0:
                return

            balance = float(acct.get("balance") or 0)
            new_balance = balance + amount

            def _update():
                return (
                    self._client.table("paper_accounts")
                    .update({"balance": new_balance})
                    .eq("id", acct["id"])
                    .eq("user_id", user_id)
                    .execute()
                )

            await _run(_update)

            def _evt():
                return (
                    self._client.table("paper_account_events").insert({
                        "account_id":       acct["id"],
                        "user_id":          user_id,
                        "trade_id":         None,
                        "event_type":       "trade_open_reserve_released",
                        "delta":            amount,
                        "realized_delta":   0,
                        "unrealized_delta": 0,
                        "balance_after":    new_balance,
                        "realized_after":   acct.get("realized_pnl") or 0,
                        "unrealized_after": acct.get("unrealized_pnl") or 0,
                        "note":             f"release failed open {symbol}",
                        "metadata":         {
                            "symbol": symbol,
                            "reservation_id": reservation_id,
                            "released_reason": reason[:200],
                            "released_event_id": event.get("id"),
                        },
                    }).execute()
                )

            await _run(_evt)
            log.warning(
                "paper_account.reservation_released",
                user_id=user_id,
                reservation_id=reservation_id,
                amount=amount,
                reason=reason[:200],
            )
        except Exception as exc:
            log.error(
                "paper_account.release_reservation_failed",
                user_id=user_id,
                reservation_id=reservation_id,
                error=str(exc)[:300],
            )
