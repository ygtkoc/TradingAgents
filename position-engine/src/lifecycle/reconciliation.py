"""
Exchange Reconciliation Service.

Compares DB trade state against actual exchange order status.
Used for:
  1. Live trades where the DB and exchange may be out of sync.
  2. Trades in 'needs_reconciliation' lifecycle_status.
  3. Periodic spot-check of live open trades.

Rules:
  - DB open, exchange filled/closed  → mark needs_reconciliation (do not auto-close)
  - DB open, exchange partially filled → update filled_quantity, write partial_fill event
  - DB closed, exchange open          → CRITICAL security_log, notify admin
  - Exchange state unknown            → mark needs_reconciliation, write security_log
  - DB and exchange both open         → OK (consistent)

NEVER auto-update trade status from reconciliation alone — human review required
for state mismatches, except for partial fill quantity updates.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.db.models import Trade
from src.exchanges.base import ExchangeAdapter, OrderResult
from src.lifecycle.action import ActionType, LifecycleAction, hold
from src.logging_config import get_logger

log = get_logger(__name__)

# Exchange statuses that mean "definitely closed/filled"
_FILLED_STATUSES  = frozenset({"filled", "closed", "done"})
# Exchange statuses that mean "partially executed"
_PARTIAL_STATUSES = frozenset({"partially_filled", "partial"})
# Exchange statuses that mean "still open / pending"
_OPEN_STATUSES    = frozenset({"open", "new", "pending"})
# Statuses that mean cancelled/rejected by exchange
_DEAD_STATUSES    = frozenset({"cancelled", "canceled", "rejected", "expired"})


@dataclass
class ReconciliationResult:
    action:       LifecycleAction
    needs_update: bool = False
    new_status: Optional[str] = None
    new_filled_quantity: Optional[float] = None
    new_avg_fill_price: Optional[float] = None
    exchange_status: Optional[str] = None
    order_result: Optional[OrderResult] = None


async def reconcile_trade(
    trade: Trade,
    adapter: ExchangeAdapter,
) -> ReconciliationResult:
    """
    Fetch exchange order status and compare with DB state.

    Args:
        trade:   The open trade to reconcile.
        adapter: Live exchange adapter (real API calls).

    Returns:
        ReconciliationResult with the action to take and any update fields.
    """
    order_id = trade.exchange_order_id
    if not order_id:
        return ReconciliationResult(
            action=LifecycleAction(
                action_type=ActionType.MARK_NEEDS_RECONCILIATION,
                reason="No exchange_order_id on live trade — cannot reconcile",
                metadata={"trigger": "missing_order_id", "trade_id": trade.id},
            )
        )

    try:
        order = await adapter.fetch_order(order_id, trade.symbol)
    except Exception as exc:
        log.error(
            "reconciliation.fetch_failed",
            trade_id=trade.id,
            order_id=order_id,
            error=str(exc)[:200],
        )
        return ReconciliationResult(
            action=LifecycleAction(
                action_type=ActionType.MARK_NEEDS_RECONCILIATION,
                reason=f"Failed to fetch order from exchange: {exc}",
                metadata={"trigger": "fetch_error", "trade_id": trade.id},
            )
        )

    exchange_status = (order.status or "unknown").lower()
    log.info(
        "reconciliation.fetched",
        trade_id=trade.id,
        order_id=order_id,
        exchange_status=exchange_status,
        db_status=trade.status,
    )

    # ── DB open + exchange filled → out of sync ───────────────────────────────
    if trade.status == "pending" and exchange_status in _FILLED_STATUSES:
        new_qty = order.filled_quantity or trade.quantity
        return ReconciliationResult(
            action=LifecycleAction(
                action_type=ActionType.UPDATE_PNL,
                reason=f"Entry order filled: filled_quantity={new_qty}",
                metadata={
                    "trigger":             "entry_order_filled",
                    "exchange_status":     exchange_status,
                    "new_status":          "open",
                    "new_filled_quantity": new_qty,
                },
            ),
            needs_update=True,
            new_status="open",
            new_filled_quantity=new_qty,
            new_avg_fill_price=order.avg_fill_price or trade.entry_price,
            exchange_status=exchange_status,
            order_result=order,
        )

    if trade.status == "pending" and exchange_status in _PARTIAL_STATUSES:
        new_qty = order.filled_quantity or 0.0
        return ReconciliationResult(
            action=LifecycleAction(
                action_type=ActionType.UPDATE_PNL,
                reason=f"Entry order partially filled: filled_quantity={new_qty}",
                metadata={
                    "trigger":             "entry_order_partial_fill",
                    "exchange_status":     exchange_status,
                    "new_status":          "open",
                    "new_filled_quantity": new_qty,
                },
            ),
            needs_update=True,
            new_status="open",
            new_filled_quantity=new_qty,
            new_avg_fill_price=order.avg_fill_price or trade.entry_price,
            exchange_status=exchange_status,
            order_result=order,
        )

    if trade.status == "pending" and exchange_status in _OPEN_STATUSES:
        return ReconciliationResult(
            action=hold(),
            exchange_status=exchange_status,
            order_result=order,
        )

    if trade.status == "pending" and exchange_status in _DEAD_STATUSES:
        return ReconciliationResult(
            action=LifecycleAction(
                action_type=ActionType.UPDATE_PNL,
                reason=f"Entry order is {exchange_status}; marking trade cancelled",
                metadata={
                    "trigger":         "entry_order_dead",
                    "exchange_status": exchange_status,
                    "new_status":      "cancelled",
                    "order_id":        order_id,
                },
            ),
            needs_update=True,
            new_status="cancelled",
            exchange_status=exchange_status,
            order_result=order,
        )

    if trade.status == "open" and exchange_status in _FILLED_STATUSES:
        # exchange_order_id is the entry order for an open position. A filled
        # entry order is normal and must not block SL/TP/trailing evaluation.
        order_qty = order.filled_quantity or 0.0
        current_qty = trade.filled_quantity or 0.0
        if order_qty > 0 and current_qty <= 0:
            return ReconciliationResult(
                action=LifecycleAction(
                    action_type=ActionType.UPDATE_PNL,
                    reason=f"Open trade entry fill reconciled: filled_quantity={order_qty}",
                    metadata={
                        "trigger":             "open_entry_order_filled",
                        "exchange_status":     exchange_status,
                        "new_filled_quantity": order_qty,
                    },
                ),
                needs_update=True,
                new_filled_quantity=order_qty,
                new_avg_fill_price=order.avg_fill_price or trade.entry_price,
                exchange_status=exchange_status,
                order_result=order,
            )
        return ReconciliationResult(
            action=hold(),
            exchange_status=exchange_status,
            order_result=order,
        )

    # ── DB open + exchange partial → update filled_quantity ───────────────────
    if trade.status == "open" and exchange_status in _PARTIAL_STATUSES:
        new_qty = order.filled_quantity or trade.effective_quantity
        return ReconciliationResult(
            action=LifecycleAction(
                action_type=ActionType.UPDATE_PNL,
                reason=f"Partial fill reconciled: filled_quantity={new_qty}",
                metadata={
                    "trigger":            "partial_fill_reconciled",
                    "exchange_status":    exchange_status,
                    "new_filled_quantity": new_qty,
                },
            ),
            needs_update=True,
            new_filled_quantity=new_qty,
            exchange_status=exchange_status,
            order_result=order,
        )

    # ── DB open + exchange open → consistent, no action ───────────────────────
    if trade.status == "open" and exchange_status in _OPEN_STATUSES:
        return ReconciliationResult(
            action=hold(),
            exchange_status=exchange_status,
            order_result=order,
        )

    # ── DB open + exchange dead (cancelled/rejected) ───────────────────────────
    if trade.status == "open" and exchange_status in _DEAD_STATUSES:
        return ReconciliationResult(
            action=LifecycleAction(
                action_type=ActionType.MARK_NEEDS_RECONCILIATION,
                reason=(
                    f"Exchange order is {exchange_status} but DB trade still open. "
                    "Manual reconciliation required."
                ),
                metadata={
                    "trigger":         "exchange_order_dead",
                    "exchange_status": exchange_status,
                    "order_id":        order_id,
                },
            ),
            exchange_status=exchange_status,
            order_result=order,
        )

    # ── DB closed + exchange open → CRITICAL ──────────────────────────────────
    if trade.status == "closed" and exchange_status in _OPEN_STATUSES:
        # This is very serious — the trade might still be open on the exchange
        return ReconciliationResult(
            action=LifecycleAction(
                action_type=ActionType.MARK_NEEDS_RECONCILIATION,
                reason=(
                    "CRITICAL: DB trade is closed but exchange order is still OPEN. "
                    "Immediate admin review required."
                ),
                metadata={
                    "trigger":         "db_closed_exchange_open",
                    "exchange_status": exchange_status,
                    "order_id":        order_id,
                    "severity":        "critical",
                },
            ),
            exchange_status=exchange_status,
            order_result=order,
        )

    # ── Unknown exchange status ───────────────────────────────────────────────
    return ReconciliationResult(
        action=LifecycleAction(
            action_type=ActionType.MARK_NEEDS_RECONCILIATION,
            reason=f"Unknown exchange order status: '{exchange_status}'",
            metadata={
                "trigger":         "unknown_exchange_status",
                "exchange_status": exchange_status,
                "order_id":        order_id,
            },
        ),
        exchange_status=exchange_status,
        order_result=order,
    )
