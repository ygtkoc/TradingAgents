"""
Tests for the exchange reconciliation service (reconciliation.py).

Covers all state machine paths:
  - DB open + exchange filled  → MARK_NEEDS_RECONCILIATION
  - DB open + exchange partial → UPDATE_PNL with new_filled_quantity
  - DB open + exchange open    → HOLD (consistent)
  - DB open + exchange dead (cancelled/rejected/expired) → MARK_NEEDS_RECONCILIATION
  - DB closed + exchange open  → CRITICAL MARK_NEEDS_RECONCILIATION
  - Unknown exchange status    → MARK_NEEDS_RECONCILIATION
  - Missing exchange_order_id  → MARK_NEEDS_RECONCILIATION
  - fetch_order raises         → MARK_NEEDS_RECONCILIATION

Never auto-closes — only the engine applies close actions.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.lifecycle.action import ActionType
from src.lifecycle.reconciliation import reconcile_trade
from src.exchanges.base import OrderResult
from tests.conftest import make_trade, run


def _mock_adapter(status: str, filled_quantity: float = 0.1, order_id: str = "ord-1") -> MagicMock:
    result = OrderResult(
        success=True,
        order_id=order_id,
        status=status,
        filled_quantity=filled_quantity,
        avg_fill_price=50_000.0,
        client_order_id=None,
        raw_response={"status": status},
    )
    adapter = MagicMock()
    adapter.fetch_order = AsyncMock(return_value=result)
    return adapter


def _error_adapter() -> MagicMock:
    adapter = MagicMock()
    adapter.fetch_order = AsyncMock(side_effect=RuntimeError("Exchange timeout"))
    return adapter


class TestReconciliation:

    # ── Missing order ID ───────────────────────────────────────────────────────

    def test_missing_order_id_needs_reconciliation(self):
        trade = make_trade(exchange_order_id=None, status="open")
        adapter = _mock_adapter("open")
        result = run(reconcile_trade(trade, adapter))
        assert result.action.action_type == ActionType.MARK_NEEDS_RECONCILIATION
        assert "missing_order_id" in str(result.action.metadata.get("trigger", ""))

    # ── DB open + exchange filled/closed/done ──────────────────────────────────

    @pytest.mark.parametrize("ex_status", ["filled", "closed", "done"])
    def test_db_open_exchange_filled_entry_order_hold(self, ex_status):
        trade = make_trade(status="open", exchange_order_id="ord-1", filled_quantity=0.1)
        adapter = _mock_adapter(ex_status)
        result = run(reconcile_trade(trade, adapter))
        assert result.action.action_type == ActionType.HOLD
        assert result.exchange_status == ex_status

    def test_db_open_exchange_filled_backfills_missing_quantity(self):
        trade = make_trade(
            status="open",
            exchange_order_id="ord-1",
            quantity=1.0,
            filled_quantity=0.0,
        )
        adapter = _mock_adapter("filled", filled_quantity=0.4)
        result = run(reconcile_trade(trade, adapter))
        assert result.action.action_type == ActionType.UPDATE_PNL
        assert result.needs_update is True
        assert result.new_filled_quantity == pytest.approx(0.4)

    # ── DB open + exchange partially_filled ────────────────────────────────────

    @pytest.mark.parametrize("ex_status", ["partially_filled", "partial"])
    def test_db_open_exchange_partial_updates_pnl(self, ex_status):
        trade = make_trade(status="open", exchange_order_id="ord-1", quantity=1.0)
        adapter = _mock_adapter(ex_status, filled_quantity=0.4)
        result = run(reconcile_trade(trade, adapter))
        assert result.action.action_type == ActionType.UPDATE_PNL
        assert result.needs_update is True
        assert result.new_filled_quantity == pytest.approx(0.4)

    # ── DB open + exchange open (consistent) ───────────────────────────────────

    @pytest.mark.parametrize("ex_status", ["open", "new", "pending"])
    def test_db_open_exchange_open_hold(self, ex_status):
        trade = make_trade(status="open", exchange_order_id="ord-1")
        adapter = _mock_adapter(ex_status)
        result = run(reconcile_trade(trade, adapter))
        assert result.action.action_type == ActionType.HOLD

    # ── DB open + exchange dead ────────────────────────────────────────────────

    @pytest.mark.parametrize("ex_status", ["cancelled", "canceled", "rejected", "expired"])
    def test_db_open_exchange_dead_needs_reconciliation(self, ex_status):
        trade = make_trade(status="open", exchange_order_id="ord-1")
        adapter = _mock_adapter(ex_status)
        result = run(reconcile_trade(trade, adapter))
        assert result.action.action_type == ActionType.MARK_NEEDS_RECONCILIATION
        assert result.exchange_status == ex_status

    # ── DB closed + exchange open ──────────────────────────────────────────────

    @pytest.mark.parametrize("ex_status", ["open", "new", "pending"])
    def test_db_closed_exchange_open_critical_reconciliation(self, ex_status):
        trade = make_trade(status="closed", exchange_order_id="ord-1")
        adapter = _mock_adapter(ex_status)
        result = run(reconcile_trade(trade, adapter))
        assert result.action.action_type == ActionType.MARK_NEEDS_RECONCILIATION
        meta = result.action.metadata
        assert meta.get("trigger") == "db_closed_exchange_open"

    # ── Unknown exchange status ────────────────────────────────────────────────

    def test_unknown_exchange_status_needs_reconciliation(self):
        trade = make_trade(status="open", exchange_order_id="ord-1")
        adapter = _mock_adapter("processing")  # not in any known set
        result = run(reconcile_trade(trade, adapter))
        assert result.action.action_type == ActionType.MARK_NEEDS_RECONCILIATION

    # ── fetch_order raises ─────────────────────────────────────────────────────

    def test_fetch_order_exception_needs_reconciliation(self):
        trade = make_trade(status="open", exchange_order_id="ord-1")
        adapter = _error_adapter()
        result = run(reconcile_trade(trade, adapter))
        assert result.action.action_type == ActionType.MARK_NEEDS_RECONCILIATION
        assert "fetch_error" in str(result.action.metadata.get("trigger", "")) or \
               "fetch" in result.action.reason.lower()

    # ── Reconciliation never returns a CLOSE action ────────────────────────────

    @pytest.mark.parametrize("ex_status", ["filled", "closed", "partially_filled", "cancelled"])
    def test_reconciliation_never_closes(self, ex_status):
        """reconcile_trade must never return a CLOSE_* action — only the engine closes."""
        trade = make_trade(status="open", exchange_order_id="ord-1")
        adapter = _mock_adapter(ex_status)
        result = run(reconcile_trade(trade, adapter))
        assert not result.action.is_close_action, (
            f"reconcile_trade returned close action for status={ex_status}: "
            f"{result.action.action_type}"
        )
