"""
PaperAccountService (close-side) — settles realised P&L on paper trade close.

Mirror of execution-engine/services/paper_account.py. Both engines own a thin
local module instead of sharing code, to avoid coupling the engines through a
shared Python package.

Settlement math:
    notional_returned = entry_price * quantity        (the original reservation)
    realised_pnl      = (exit - entry) * qty * sign(direction)
    delta             = notional_returned + realised_pnl

    paper_accounts.balance      += delta
    paper_accounts.realized_pnl += realised_pnl

A `paper_account_events` row is appended for the audit ledger.

Best-effort: an exception NEVER blocks the close. The trade is already marked
closed by the lifecycle engine before this service is called; failure here
only affects the ledger and is logged for reconciliation.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from src.db.supabase_client import get_client
from src.logging_config import get_logger

log = get_logger(__name__)


async def _run(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


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

    async def settle_close(
        self,
        *,
        user_id:      str,
        trade_id:     str,
        symbol:       str,
        entry_price:  float,
        exit_price:   float,
        quantity:     float,
        direction:    str,            # "long" | "short" | "neutral"
        realized_pnl: float,
    ) -> None:
        """Best-effort: never raises. On failure, logs and the lifecycle close
        proceeds — reconciliation can repair the ledger out of band."""
        try:
            acct = await self.get_account(user_id)
            if acct is None:
                log.warning("paper_account.no_account_on_close",
                            user_id=user_id, trade_id=trade_id)
                return

            notional   = float(entry_price) * float(quantity)
            delta      = notional + float(realized_pnl)
            balance    = float(acct.get("balance") or 0)
            realised   = float(acct.get("realized_pnl") or 0)

            new_balance  = balance + delta
            new_realised = realised + float(realized_pnl)

            def _update():
                return (
                    self._client.table("paper_accounts")
                    .update({
                        "balance":      new_balance,
                        "realized_pnl": new_realised,
                    })
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
                        "trade_id":         trade_id,
                        "event_type":       "trade_close_settle",
                        "delta":            delta,
                        "realized_delta":   float(realized_pnl),
                        "unrealized_delta": 0,
                        "balance_after":    new_balance,
                        "realized_after":   new_realised,
                        "unrealized_after": float(acct.get("unrealized_pnl") or 0),
                        "note":             f"close {symbol}",
                        "metadata": {
                            "symbol":      symbol,
                            "direction":   direction,
                            "entry":       entry_price,
                            "exit":        exit_price,
                            "quantity":    quantity,
                            "notional":    notional,
                            "realized_pnl": realized_pnl,
                        },
                    }).execute()
                )
            await _run(_evt)

            log.info(
                "paper_account.settled",
                user_id=user_id, trade_id=trade_id, symbol=symbol,
                realized_pnl=realized_pnl, balance_after=new_balance,
            )

        except Exception as exc:
            log.error(
                "paper_account.settle_failed",
                user_id=user_id, trade_id=trade_id, error=str(exc)[:300],
            )
