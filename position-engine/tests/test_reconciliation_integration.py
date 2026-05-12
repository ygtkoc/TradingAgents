"""
End-to-end tests for the reconciliation integration in LifecycleEngine.

These tests verify the audit-required behaviour:

  1. Reconciliation runs BEFORE SL/TP/trailing for live trades.
  2. Partial-fill reconciliation updates filled_quantity (only allowed auto-fix).
  3. Unknown exchange status → mark_needs_reconciliation + security_log.
  4. db_open_exchange_filled (DB open, exchange filled) → reconciliation triggered.
  5. A non-HOLD reconciliation result STOPS the pipeline (no SL/TP eval).
  6. Retry limit blocks processing in claim_for_lifecycle.
  7. lifecycle_status='needs_reconciliation' skips SL/TP and only runs recon.

Engine-level tests use the same `_make_engine()` mocking strategy as
test_lifecycle_engine.py. Repository-level tests mock the supabase client.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db.models import LifecycleStatus, Trade
from src.lifecycle.action import ActionType, LifecycleAction, hold
from src.lifecycle.engine import LifecycleEngine
from src.lifecycle.reconciliation import ReconciliationResult
from tests.conftest import (
    make_bot,
    make_exchange_account,
    make_platform_settings,
    make_snapshot,
    make_trade,
    make_user_settings,
)


# ── Engine fixture (same shape as test_lifecycle_engine.py) ────────────────────

def _make_engine() -> LifecycleEngine:
    """Build a LifecycleEngine with all repos/services mocked."""
    engine = LifecycleEngine.__new__(LifecycleEngine)

    engine._lifecycle_repo = MagicMock()
    engine._lifecycle_repo.count_critical_security_events = AsyncMock(return_value=0)
    engine._lifecycle_repo.release_claim = AsyncMock()
    engine._lifecycle_repo.update_trade  = AsyncMock()
    engine._lifecycle_repo.mark_closed   = AsyncMock()
    engine._lifecycle_repo.mark_needs_reconciliation = AsyncMock()
    engine._lifecycle_repo.mark_failed   = AsyncMock()
    engine._lifecycle_repo.get_by_id     = AsyncMock(return_value=None)

    engine._context_repo  = MagicMock()
    engine._context_repo.get_bot           = AsyncMock(return_value=make_bot(status="active"))
    engine._context_repo.get_user_settings = AsyncMock(return_value=make_user_settings())
    engine._context_repo.get_exchange_account = AsyncMock(
        return_value=make_exchange_account()
    )

    engine._platform_repo = MagicMock()
    engine._platform_repo.get = AsyncMock(return_value=make_platform_settings())

    engine._event_repo    = MagicMock()
    engine._event_repo.create      = AsyncMock()
    engine._event_repo.bulk_create = AsyncMock()

    engine._risk_log     = MagicMock(); engine._risk_log.create     = AsyncMock()
    engine._security_log = MagicMock(); engine._security_log.create = AsyncMock()
    engine._audit_log    = MagicMock(); engine._audit_log.create    = AsyncMock()

    engine._security_guard = MagicMock()
    from src.guards.lifecycle_security_guard import LifecycleSecurityGuardResult
    engine._security_guard.check = MagicMock(return_value=LifecycleSecurityGuardResult(
        blocked=False, reason="ok", checks=[]
    ))

    engine._risk_guard = MagicMock()
    from src.guards.lifecycle_risk_guard import LifecycleRiskGuardResult
    engine._risk_guard.check_before_close = MagicMock(return_value=LifecycleRiskGuardResult(
        blocked=False, reason="ok"
    ))

    engine._market_data = MagicMock()
    engine._market_data.get_snapshot = AsyncMock(return_value=make_snapshot(close_price=50_000.0))

    engine._notifications = MagicMock()
    engine._notifications.trade_closed             = AsyncMock()
    engine._notifications.emergency_triggered      = AsyncMock()
    engine._notifications.reconciliation_required  = AsyncMock()
    engine._notifications.pnl_updated              = AsyncMock()

    engine._recovery = MagicMock()
    engine._recovery.handle_stuck_closing = AsyncMock()

    engine._key_provider = MagicMock()
    creds = MagicMock()
    creds.api_key = "k"
    creds.api_secret = "s"
    creds.zero_out = MagicMock()
    engine._key_provider.get_credentials = AsyncMock(return_value=creds)

    return engine


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# Helpers for crafting recon results
def _recon_hold() -> ReconciliationResult:
    return ReconciliationResult(action=hold(), exchange_status="open")


def _recon_needs_recon(trigger: str, reason: str = "anomaly") -> ReconciliationResult:
    return ReconciliationResult(
        action=LifecycleAction(
            action_type=ActionType.MARK_NEEDS_RECONCILIATION,
            reason=reason,
            metadata={"trigger": trigger},
        ),
        exchange_status="filled" if "filled" in trigger else "unknown",
    )


def _recon_partial(new_qty: float = 0.05) -> ReconciliationResult:
    return ReconciliationResult(
        action=LifecycleAction(
            action_type=ActionType.UPDATE_PNL,
            reason=f"Partial fill reconciled: filled_quantity={new_qty}",
            metadata={"trigger": "partial_fill_reconciled"},
        ),
        needs_update=True,
        new_filled_quantity=new_qty,
        exchange_status="partially_filled",
    )


# ── 1. Reconciliation runs BEFORE SL/TP ───────────────────────────────────────

class TestReconciliationRunsBeforeTriggers:
    def test_recon_anomaly_blocks_sl_check(self):
        """Live trade with stop-loss triggered AND recon anomaly → recon wins."""
        engine = _make_engine()
        # Price would trigger SL (long, price 48k, stop 49k)
        engine._market_data.get_snapshot = AsyncMock(
            return_value=make_snapshot(close_price=48_000.0)
        )
        trade = make_trade(
            mode="live",
            direction="long",
            entry_price=50_000.0,
            stop_loss=49_000.0,
            quantity=1.0,
            exchange_order_id="ord-123",
        )

        with patch(
            "src.lifecycle.engine.reconcile_trade",
            AsyncMock(return_value=_recon_needs_recon("db_open_exchange_filled")),
        ):
            with patch("src.lifecycle.engine.get_live_adapter", MagicMock()):
                run(engine._run_pipeline(trade))

        # mark_needs_reconciliation was called from _apply_action path
        engine._lifecycle_repo.mark_needs_reconciliation.assert_awaited_once()
        # mark_closed was NOT called (no SL trigger executed)
        engine._lifecycle_repo.mark_closed.assert_not_awaited()


# ── 2. Partial-fill reconciliation updates quantity ────────────────────────────

class TestPartialFillUpdate:
    def test_partial_fill_calls_update_with_new_quantity(self):
        engine = _make_engine()
        trade = make_trade(
            mode="live",
            direction="long",
            quantity=0.1,
            exchange_order_id="ord-partial",
        )

        with patch(
            "src.lifecycle.engine.reconcile_trade",
            AsyncMock(return_value=_recon_partial(new_qty=0.05)),
        ):
            with patch("src.lifecycle.engine.get_live_adapter", MagicMock()):
                run(engine._run_pipeline(trade))

        # update_trade called with filled_quantity=0.05
        calls = engine._lifecycle_repo.update_trade.await_args_list
        assert any(
            getattr(call.args[1], "filled_quantity", None) == 0.05
            for call in calls
        ), f"Expected filled_quantity=0.05 update, got: {calls}"

    def test_partial_fill_does_not_close_trade(self):
        engine = _make_engine()
        trade = make_trade(mode="live", direction="long", exchange_order_id="ord-1")

        with patch(
            "src.lifecycle.engine.reconcile_trade",
            AsyncMock(return_value=_recon_partial(new_qty=0.07)),
        ):
            with patch("src.lifecycle.engine.get_live_adapter", MagicMock()):
                run(engine._run_pipeline(trade))

        engine._lifecycle_repo.mark_closed.assert_not_awaited()


# ── 3. Unknown exchange status → needs_reconciliation + security_log ──────────

class TestUnknownExchangeStatus:
    def test_unknown_status_marks_reconciliation(self):
        engine = _make_engine()
        trade = make_trade(mode="live", direction="long", exchange_order_id="ord-?")

        with patch(
            "src.lifecycle.engine.reconcile_trade",
            AsyncMock(return_value=_recon_needs_recon("unknown_exchange_status")),
        ):
            with patch("src.lifecycle.engine.get_live_adapter", MagicMock()):
                run(engine._run_pipeline(trade))

        engine._lifecycle_repo.mark_needs_reconciliation.assert_awaited_once()

    def test_unknown_status_writes_security_log(self):
        engine = _make_engine()
        trade = make_trade(mode="live", direction="long", exchange_order_id="ord-?")

        with patch(
            "src.lifecycle.engine.reconcile_trade",
            AsyncMock(return_value=_recon_needs_recon("unknown_exchange_status")),
        ):
            with patch("src.lifecycle.engine.get_live_adapter", MagicMock()):
                run(engine._run_pipeline(trade))

        engine._security_log.create.assert_awaited()
        engine._audit_log.create.assert_awaited()


# ── 4. DB open + exchange filled → reconciliation triggered ───────────────────

class TestDbOpenExchangeFilled:
    def test_db_open_exchange_filled_marks_reconciliation(self):
        engine = _make_engine()
        trade = make_trade(mode="live", direction="long", exchange_order_id="ord-x")

        with patch(
            "src.lifecycle.engine.reconcile_trade",
            AsyncMock(return_value=_recon_needs_recon("db_open_exchange_filled")),
        ):
            with patch("src.lifecycle.engine.get_live_adapter", MagicMock()):
                run(engine._run_pipeline(trade))

        engine._lifecycle_repo.mark_needs_reconciliation.assert_awaited_once()
        # No close was attempted
        engine._lifecycle_repo.mark_closed.assert_not_awaited()


# ── 5. Reconciliation stops the pipeline ─────────────────────────────────────

class TestReconciliationStopsPipeline:
    def test_non_hold_recon_skips_normal_triggers(self):
        """Even with a price that should trigger TP, recon anomaly stops pipeline."""
        engine = _make_engine()
        engine._market_data.get_snapshot = AsyncMock(
            return_value=make_snapshot(close_price=60_000.0)  # would trigger TP
        )
        trade = make_trade(
            mode="live",
            direction="long",
            entry_price=50_000.0,
            take_profit=58_000.0,
            quantity=1.0,
            exchange_order_id="ord-tp",
        )

        with patch(
            "src.lifecycle.engine.reconcile_trade",
            AsyncMock(return_value=_recon_needs_recon("unknown_exchange_status")),
        ):
            with patch("src.lifecycle.engine.get_live_adapter", MagicMock()):
                run(engine._run_pipeline(trade))

        # No close happened — TP trigger never evaluated
        engine._lifecycle_repo.mark_closed.assert_not_awaited()
        engine._lifecycle_repo.mark_needs_reconciliation.assert_awaited_once()


# ── 6. Retry limit blocks processing ──────────────────────────────────────────

class TestRetryLimit:
    """Repository-level: claim_for_lifecycle must enforce position_max_retries."""

    def _make_repo_with_returned_count(self, retry_count: int):
        from src.db.repositories import TradeLifecycleRepository
        repo = TradeLifecycleRepository.__new__(TradeLifecycleRepository)
        repo._client = MagicMock()

        # Return a row with the given retry count from the atomic UPDATE
        row = {
            "id": "trade-1", "user_id": "u-1", "bot_id": "b-1",
            "exchange": "binance", "symbol": "BTC/USDT",
            "side": "buy", "direction": "long", "mode": "live",
            "status": "open", "entry_price": 50_000.0, "quantity": 0.1,
            "lifecycle_status": "monitoring",
            "lifecycle_retry_count": retry_count,
            "created_at": "2025-01-01T00:00:00+00:00",
        }
        upd_resp = MagicMock(); upd_resp.data = [row]

        # Build a chainable update mock
        chain = MagicMock()
        chain.update.return_value = chain
        chain.eq.return_value = chain
        chain.in_.return_value = chain
        chain.execute.return_value = upd_resp
        repo._client.table.return_value = chain

        return repo

    def test_retry_count_below_limit_returns_trade(self):
        from src.config import settings
        repo = self._make_repo_with_returned_count(retry_count=0)
        # Stub the retry bump and mark_failed so they don't blow up
        repo._bump_retry_count = AsyncMock()
        repo.mark_failed = AsyncMock()

        with patch.object(settings, "position_max_retries", 5):
            trade = run(repo.claim_for_lifecycle("trade-1", "worker-1"))

        assert trade is not None
        assert trade.lifecycle_retry_count == 1
        repo.mark_failed.assert_not_awaited()

    def test_retry_count_at_limit_marks_failed_and_returns_none(self):
        from src.config import settings
        # retry_count=5, max=5 → new_retry=6 > 5 → exceeded
        repo = self._make_repo_with_returned_count(retry_count=5)
        repo._bump_retry_count = AsyncMock()
        repo.mark_failed = AsyncMock()

        with patch.object(settings, "position_max_retries", 5):
            trade = run(repo.claim_for_lifecycle("trade-1", "worker-1"))

        assert trade is None
        repo.mark_failed.assert_awaited_once()
        # mark_failed message should mention max retries
        call = repo.mark_failed.await_args
        assert "max retries" in call.args[1].lower()

    def test_retry_count_far_above_limit_marks_failed(self):
        from src.config import settings
        repo = self._make_repo_with_returned_count(retry_count=99)
        repo._bump_retry_count = AsyncMock()
        repo.mark_failed = AsyncMock()

        with patch.object(settings, "position_max_retries", 3):
            trade = run(repo.claim_for_lifecycle("trade-1", "worker-1"))

        assert trade is None
        repo.mark_failed.assert_awaited_once()


# ── 7. needs_reconciliation skips normal lifecycle ────────────────────────────

class TestNeedsReconciliationSkipsNormalLogic:
    def test_needs_recon_status_runs_only_recon(self):
        """Trade in needs_reconciliation must NOT evaluate SL/TP/trailing."""
        engine = _make_engine()
        # Price that would normally trigger SL
        engine._market_data.get_snapshot = AsyncMock(
            return_value=make_snapshot(close_price=48_000.0)
        )
        # Trade is in needs_reconciliation status — even with SL conditions
        trade = make_trade(
            mode="live",
            direction="long",
            entry_price=50_000.0,
            stop_loss=49_000.0,
            quantity=1.0,
            exchange_order_id="ord-recon",
            lifecycle_status=LifecycleStatus.NEEDS_RECONCILIATION.value,
        )

        # Recon returns HOLD (DB and exchange both open)
        with patch(
            "src.lifecycle.engine.reconcile_trade",
            AsyncMock(return_value=_recon_hold()),
        ):
            with patch("src.lifecycle.engine.get_live_adapter", MagicMock()):
                run(engine._run_pipeline(trade))

        # NO close should have happened — SL never evaluated
        engine._lifecycle_repo.mark_closed.assert_not_awaited()
        # Claim was released (back to idle for next clean cycle)
        engine._lifecycle_repo.release_claim.assert_awaited()

    def test_needs_recon_anomaly_marks_needs_reconciliation(self):
        """needs_reconciliation + recon still anomalous → mark_needs_reconciliation."""
        engine = _make_engine()
        trade = make_trade(
            mode="live",
            direction="long",
            exchange_order_id="ord-recon",
            lifecycle_status=LifecycleStatus.NEEDS_RECONCILIATION.value,
        )

        with patch(
            "src.lifecycle.engine.reconcile_trade",
            AsyncMock(return_value=_recon_needs_recon("db_closed_exchange_open")),
        ):
            with patch("src.lifecycle.engine.get_live_adapter", MagicMock()):
                run(engine._run_pipeline(trade))

        engine._lifecycle_repo.mark_needs_reconciliation.assert_awaited_once()
        engine._lifecycle_repo.mark_closed.assert_not_awaited()
        # CRITICAL severity log was written
        engine._security_log.create.assert_awaited()


# ── 8. Paper trades skip reconciliation entirely ──────────────────────────────

class TestPaperSkipsReconciliation:
    def test_paper_trade_does_not_call_reconcile(self):
        engine = _make_engine()
        trade = make_trade(mode="paper", direction="long", exchange_order_id="ord-1")

        with patch("src.lifecycle.engine.reconcile_trade", AsyncMock()) as recon_mock:
            with patch("src.lifecycle.engine.get_live_adapter", MagicMock()):
                run(engine._run_pipeline(trade))

        recon_mock.assert_not_awaited()


# ── 9. Live trade with NO exchange_order_id skips recon ───────────────────────

class TestLiveNoOrderIdSkipsReconciliation:
    def test_live_no_order_id_does_not_call_reconcile(self):
        engine = _make_engine()
        trade = make_trade(mode="live", direction="long", exchange_order_id=None)

        with patch("src.lifecycle.engine.reconcile_trade", AsyncMock()) as recon_mock:
            with patch("src.lifecycle.engine.get_live_adapter", MagicMock()):
                run(engine._run_pipeline(trade))

        recon_mock.assert_not_awaited()
