"""
End-to-end tests for LifecycleEngine (lifecycle/engine.py).

The engine is tested with all external dependencies mocked:
  - DB repositories (lifecycle, context, events, logs, platform_settings)
  - MarketDataService
  - NotificationService
  - KeyProvider
  - Exchange adapters

Tests cover:
  - HOLD: no trigger, claim released
  - UPDATE_PNL: pnl written, claim released
  - UPDATE_TRAILING_STOP: stop updated, claim released
  - CLOSE_STOP_LOSS: simulated close (paper) completes correctly
  - CLOSE_TAKE_PROFIT: simulated close (paper) completes correctly
  - CLOSE_EMERGENCY (kill switch): paper close completes
  - Stuck 'closing' state → RecoveryService.handle_stuck_closing called
  - No valid price → event written, claim released
  - Security guard blocked → claim released, no close attempted
  - Lifecycle engine never creates trades, only updates existing ones
  - Live close: disabled by default (ENABLE_LIVE_CLOSE=false)
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.lifecycle.action import ActionType
from src.lifecycle.engine import LifecycleEngine
from src.db.models import LifecycleStatus
from tests.conftest import (
    make_trade,
    make_bot,
    make_user_settings,
    make_exchange_account,
    make_platform_settings,
    make_snapshot,
)
from src.db.repositories import _is_transient_lifecycle_error


# ── Fixtures and helpers ───────────────────────────────────────────────────────

def _make_engine():
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
    engine._context_repo.get_bot            = AsyncMock(return_value=make_bot(status="active"))
    engine._context_repo.get_user_settings  = AsyncMock(return_value=make_user_settings())
    engine._context_repo.get_exchange_account = AsyncMock(return_value=make_exchange_account())

    engine._platform_repo = MagicMock()
    engine._platform_repo.get = AsyncMock(return_value=make_platform_settings())

    engine._event_repo    = MagicMock()
    engine._event_repo.create      = AsyncMock()
    engine._event_repo.bulk_create = AsyncMock()

    engine._risk_log      = MagicMock()
    engine._risk_log.create = AsyncMock()

    engine._security_log  = MagicMock()
    engine._security_log.create = AsyncMock()

    engine._audit_log     = MagicMock()
    engine._audit_log.create = AsyncMock()

    engine._security_guard = MagicMock()
    # Default: security guard passes
    from src.guards.lifecycle_security_guard import LifecycleSecurityGuardResult, SecurityCheckResult
    engine._security_guard.check = MagicMock(return_value=LifecycleSecurityGuardResult(
        blocked=False, reason="all checks passed", checks=[]
    ))

    engine._risk_guard = MagicMock()
    from src.guards.lifecycle_risk_guard import LifecycleRiskGuardResult
    engine._risk_guard.check_before_close = MagicMock(return_value=LifecycleRiskGuardResult(
        blocked=False, reason="ok"
    ))

    engine._market_data   = MagicMock()
    engine._market_data.get_snapshot = AsyncMock(return_value=make_snapshot(close_price=50_000.0))

    engine._notifications = MagicMock()
    engine._notifications.trade_closed             = AsyncMock()
    engine._notifications.emergency_triggered      = AsyncMock()
    engine._notifications.reconciliation_required  = AsyncMock()
    engine._notifications.pnl_updated              = AsyncMock()

    engine._recovery = MagicMock()
    engine._recovery.handle_stuck_closing = AsyncMock()

    engine._key_provider = MagicMock()

    return engine


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── Stuck 'closing' state ──────────────────────────────────────────────────────

class TestStuckClosing:
    def test_stuck_closing_calls_recovery(self):
        engine = _make_engine()
        trade  = make_trade(lifecycle_status=LifecycleStatus.CLOSING.value, mode="paper")
        run(engine._run_pipeline(trade))
        engine._recovery.handle_stuck_closing.assert_awaited_once_with(trade)

    def test_stuck_closing_does_not_proceed_to_triggers(self):
        engine = _make_engine()
        trade  = make_trade(lifecycle_status=LifecycleStatus.CLOSING.value, mode="paper")
        run(engine._run_pipeline(trade))
        # Security guard should NOT be called (short-circuits at step 0)
        engine._security_guard.check.assert_not_called()


# ── Price unavailable ──────────────────────────────────────────────────────────

class TestNoPriceAvailable:
    def test_no_price_writes_event_and_releases_claim(self):
        engine = _make_engine()
        engine._market_data.get_snapshot = AsyncMock(return_value=None)
        trade = make_trade(mode="paper")
        run(engine._run_pipeline(trade))
        engine._lifecycle_repo.release_claim.assert_awaited_once_with(trade.id)
        engine._event_repo.create.assert_awaited()


# ── Security guard blocked ─────────────────────────────────────────────────────

class TestSecurityGuardBlocked:
    def test_blocked_releases_claim_without_closing(self):
        from src.guards.lifecycle_security_guard import LifecycleSecurityGuardResult
        engine = _make_engine()
        engine._security_guard.check = MagicMock(return_value=LifecycleSecurityGuardResult(
            blocked=True, reason="test block", checks=[]
        ))
        trade = make_trade(mode="paper")
        run(engine._run_pipeline(trade))
        engine._lifecycle_repo.release_claim.assert_awaited()
        engine._lifecycle_repo.mark_closed.assert_not_awaited()


# ── HOLD action ────────────────────────────────────────────────────────────────

class TestHoldAction:
    def test_hold_releases_claim(self):
        engine = _make_engine()
        # No SL/TP/trailing → should HOLD after P&L update
        trade = make_trade(mode="paper", stop_loss=None, take_profit=None)
        run(engine._run_pipeline(trade))
        # Either release_claim or update_trade is called (depends on pnl update)
        assert (
            engine._lifecycle_repo.release_claim.await_count > 0 or
            engine._lifecycle_repo.update_trade.await_count > 0
        )


# ── UPDATE_PNL action ──────────────────────────────────────────────────────────

class TestUpdatePnlAction:
    def test_pnl_update_writes_event_and_releases(self):
        engine = _make_engine()
        trade = make_trade(
            mode="paper",
            direction="long",
            entry_price=50_000.0,
            quantity=1.0,
            stop_loss=None,
            take_profit=None,
        )
        run(engine._run_pipeline(trade))
        # At minimum, a pnl_updated or price_checked event is written
        assert engine._event_repo.create.await_count >= 1
        # Claim is released
        engine._lifecycle_repo.release_claim.assert_awaited()

    def test_pnl_update_writes_percentage_and_current_pnl(self):
        engine = _make_engine()
        engine._market_data.get_snapshot = AsyncMock(
            return_value=make_snapshot(close_price=51_000.0)
        )
        trade = make_trade(
            mode="paper",
            direction="long",
            entry_price=50_000.0,
            quantity=0.1,
            stop_loss=None,
            take_profit=None,
        )
        run(engine._run_pipeline(trade))
        update = engine._lifecycle_repo.update_trade.await_args.args[1]
        assert update.unrealized_pnl == 100.0
        assert update.pnl == 100.0
        assert update.pnl_pct == 2.0


# ── Paper close (CLOSE_STOP_LOSS) ──────────────────────────────────────────────

class TestPaperCloseStopLoss:
    def test_paper_stop_loss_fast_path_closes_before_security_guard(self):
        engine = _make_engine()
        engine._market_data.get_snapshot = AsyncMock(
            return_value=make_snapshot(close_price=48_000.0)
        )
        trade = make_trade(
            mode="paper",
            direction="long",
            entry_price=50_000.0,
            stop_loss=49_000.0,
            quantity=1.0,
        )

        run(engine._run_pipeline(trade))

        engine._lifecycle_repo.mark_closed.assert_awaited_once()
        engine._security_guard.check.assert_not_called()
        engine._context_repo.get_bot.assert_not_awaited()

    def test_stop_loss_triggers_paper_close(self):
        engine = _make_engine()
        # Price=48_000, stop_loss=49_000 → long stop-loss trigger
        engine._market_data.get_snapshot = AsyncMock(
            return_value=make_snapshot(close_price=48_000.0)
        )
        trade = make_trade(
            mode="paper",
            direction="long",
            entry_price=50_000.0,
            stop_loss=49_000.0,
            quantity=1.0,
        )
        run(engine._run_pipeline(trade))
        engine._lifecycle_repo.mark_closed.assert_awaited_once()

    def test_short_stop_loss_triggers_on_candle_high_even_if_close_below_stop(self):
        engine = _make_engine()
        engine._market_data.get_snapshot = AsyncMock(
            return_value=make_snapshot(
                symbol="XLM/USDT",
                open_price=0.2093,
                high_price=0.2096,
                low_price=0.2088,
                close_price=0.2092,
            )
        )
        trade = make_trade(
            mode="paper",
            symbol="XLM/USDT",
            direction="short",
            side="sell",
            entry_price=0.2051,
            avg_fill_price=0.2051,
            stop_loss=0.209202,
            quantity=4875.67040468,
            filled_quantity=4875.67040468,
        )

        run(engine._run_pipeline(trade))

        engine._lifecycle_repo.mark_closed.assert_awaited_once()
        kwargs = engine._lifecycle_repo.mark_closed.await_args.kwargs
        assert kwargs["close_reason"] == "stop_loss"
        assert kwargs["exit_price"] == pytest.approx(0.209202)

    def test_paper_close_does_not_call_exchange(self):
        engine = _make_engine()
        engine._market_data.get_snapshot = AsyncMock(
            return_value=make_snapshot(close_price=48_000.0)
        )
        trade = make_trade(
            mode="paper",
            direction="long",
            stop_loss=49_000.0,
            quantity=1.0,
        )
        run(engine._run_pipeline(trade))
        # Key provider should NOT have been called (no real exchange)
        engine._key_provider.get_credentials.assert_not_called()

    def test_paper_close_sends_notification(self):
        engine = _make_engine()
        engine._market_data.get_snapshot = AsyncMock(
            return_value=make_snapshot(close_price=48_000.0)
        )
        closed_trade = make_trade(mode="paper", status="closed", realized_pnl=-200.0)
        engine._lifecycle_repo.get_by_id = AsyncMock(return_value=closed_trade)
        trade = make_trade(
            mode="paper",
            direction="long",
            stop_loss=49_000.0,
        )
        run(engine._run_pipeline(trade))
        engine._notifications.trade_closed.assert_awaited_once()

    def test_paper_close_persists_r_multiple(self):
        engine = _make_engine()
        engine._market_data.get_snapshot = AsyncMock(
            return_value=make_snapshot(close_price=52_000.0)
        )
        trade = make_trade(
            mode="paper",
            direction="long",
            entry_price=50_000.0,
            take_profit=51_000.0,
            quantity=0.1,
            risk_amount=100.0,
        )
        run(engine._run_pipeline(trade))
        kwargs = engine._lifecycle_repo.mark_closed.await_args.kwargs
        assert kwargs["realized_pnl"] == 200.0
        assert kwargs["pnl_pct"] == 4.0
        assert kwargs["r_multiple"] == 2.0

    def test_final_scaled_tp_keeps_prior_realized_pnl(self):
        engine = _make_engine()
        engine._market_data.get_snapshot = AsyncMock(
            return_value=make_snapshot(close_price=103.0)
        )
        plan = {
            "mode": "scaled_take_profit",
            "levels": [
                {"level": 1, "label": "TP1", "price": 101.0, "status": "hit"},
                {"level": 2, "label": "TP2", "price": 102.0, "status": "hit"},
                {"level": 3, "label": "TP3", "price": 103.0, "status": "pending"},
            ],
        }
        trade = make_trade(
            mode="paper",
            direction="long",
            entry_price=100.0,
            take_profit=103.0,
            quantity=10.0,
            filled_quantity=4.0,
            realized_pnl=10.0,
            risk_amount=10.0,
            metadata={
                "reward_plan": plan,
                "initial_quantity": 10.0,
                "reserved_on_open": False,
            },
        )

        run(engine._run_pipeline(trade))

        kwargs = engine._lifecycle_repo.mark_closed.await_args.kwargs
        assert kwargs["realized_pnl"] == pytest.approx(22.0)
        assert kwargs["r_multiple"] == pytest.approx(2.2)


# ── Paper close (CLOSE_TAKE_PROFIT) ───────────────────────────────────────────

class TestPaperCloseTakeProfit:
    def test_take_profit_triggers_paper_close(self):
        engine = _make_engine()
        # Price=60_000, take_profit=58_000 → long take-profit trigger
        engine._market_data.get_snapshot = AsyncMock(
            return_value=make_snapshot(close_price=60_000.0)
        )
        trade = make_trade(
            mode="paper",
            direction="long",
            entry_price=50_000.0,
            take_profit=58_000.0,
            quantity=1.0,
        )
        run(engine._run_pipeline(trade))
        engine._lifecycle_repo.mark_closed.assert_awaited_once()


# ── Emergency close (kill switch) ──────────────────────────────────────────────

    def test_missing_reward_plan_partial_closes_and_moves_stop(self):
        engine = _make_engine()
        engine._market_data.get_snapshot = AsyncMock(
            return_value=make_snapshot(close_price=102.1)
        )
        trade = make_trade(
            mode="paper",
            direction="long",
            entry_price=100.0,
            stop_loss=98.0,
            take_profit=106.0,
            quantity=10.0,
            filled_quantity=10.0,
            risk_reward_ratio=3.0,
            risk_amount=20.0,
            metadata={"reserved_on_open": False},
        )

        run(engine._run_pipeline(trade))

        engine._lifecycle_repo.mark_closed.assert_not_awaited()
        update = engine._lifecycle_repo.update_trade.await_args.args[1]
        assert update.filled_quantity == pytest.approx(7.0)
        assert update.realized_pnl == pytest.approx(6.3)
        assert update.stop_loss == pytest.approx(100.0)
        assert update.take_profit == pytest.approx(103.9)
        assert update.metadata["reward_plan"]["source"] == "position_engine_fallback"


class TestPaperRiskNormalization:
    def test_oversized_wallet_risk_is_repaired_before_pnl_stop(self):
        engine = _make_engine()
        engine._paper_account = MagicMock()
        engine._paper_account.get_account = AsyncMock(return_value={"balance": 1_000.0})
        engine._paper_account.settle_close = AsyncMock()
        engine._paper_account.sync_unrealized = AsyncMock()
        engine._market_data.get_snapshot = AsyncMock(
            return_value=make_snapshot(close_price=98.0)
        )
        trade = make_trade(
            mode="paper",
            direction="long",
            entry_price=100.0,
            avg_fill_price=100.0,
            stop_loss=80.0,
            take_profit=150.0,
            quantity=10.0,
            filled_quantity=10.0,
            risk_amount=200.0,
            risk_percent=2.0,
            risk_reward_ratio=2.0,
            metadata={"reserved_on_open": False},
        )

        run(engine._run_pipeline(trade))

        repair_update = engine._lifecycle_repo.update_trade.await_args_list[0].args[1]
        assert repair_update.risk_amount == pytest.approx(20.0)
        engine._lifecycle_repo.mark_closed.assert_awaited_once()
        assert engine._lifecycle_repo.mark_closed.await_args.kwargs["close_reason"] == "stop_loss"


class TestEmergencyClose:
    def test_kill_switch_triggers_emergency_close(self):
        engine = _make_engine()
        ps = make_platform_settings(global_trading_enabled=False)
        engine._platform_repo.get = AsyncMock(return_value=ps)
        trade = make_trade(mode="paper", direction="long")
        run(engine._run_pipeline(trade))
        # Should write an event and close the trade
        engine._lifecycle_repo.mark_closed.assert_awaited_once()

    def test_kill_switch_writes_risk_log(self):
        engine = _make_engine()
        ps = make_platform_settings(global_trading_enabled=False)
        engine._platform_repo.get = AsyncMock(return_value=ps)
        trade = make_trade(mode="paper", direction="long")
        run(engine._run_pipeline(trade))
        engine._risk_log.create.assert_awaited()


# ── Live close disabled by default ────────────────────────────────────────────

class TestLiveCloseDisabledByDefault:
    def test_live_close_blocked_when_flag_is_false(self):
        """With ENABLE_LIVE_CLOSE=false (default), live close should not submit orders."""
        engine = _make_engine()
        from src.guards.lifecycle_security_guard import LifecycleSecurityGuardResult, SecurityCheckResult
        # The security guard (for live close) blocks because live_close env gate is false
        engine._security_guard.check = MagicMock(side_effect=[
            # First call (main pipeline check) passes
            LifecycleSecurityGuardResult(blocked=False, reason="ok", checks=[]),
            # Second call (live close specific) blocks
            LifecycleSecurityGuardResult(
                blocked=True,
                reason="ENABLE_LIVE_CLOSE=false",
                checks=[SecurityCheckResult(
                    name="live_close_gate_env",
                    passed=False,
                    message="ENABLE_LIVE_CLOSE=false",
                )],
            ),
        ])
        engine._market_data.get_snapshot = AsyncMock(
            return_value=make_snapshot(close_price=48_000.0)
        )
        trade = make_trade(
            mode="live",
            direction="long",
            stop_loss=49_000.0,
        )
        run(engine._run_pipeline(trade))
        # Key provider must NOT have been called (no credentials loaded)
        engine._key_provider.get_credentials.assert_not_called()
        # Trade must NOT be marked closed via mark_closed (close was blocked)
        engine._lifecycle_repo.mark_closed.assert_not_awaited()


# ── Lifecycle never creates new trades ──────────────────────────────────────────

class TestNoNewTradeCreation:
    def test_engine_never_calls_trade_create(self):
        """LifecycleEngine must only update existing trades, never create them."""
        engine = _make_engine()
        trade = make_trade(mode="paper", stop_loss=49_000.0, direction="long")
        engine._market_data.get_snapshot = AsyncMock(
            return_value=make_snapshot(close_price=48_000.0)
        )
        run(engine._run_pipeline(trade))
        # No trade creation method should exist on lifecycle_repo or be called
        assert not hasattr(engine._lifecycle_repo, "create") or \
               not engine._lifecycle_repo.create.called


# ── Unhandled exception → mark_failed ─────────────────────────────────────────

class TestUnhandledException:
    def test_paper_timeout_releases_claim_without_reconciliation_pause(self):
        engine = _make_engine()
        trade = make_trade(mode="paper")
        with patch("src.lifecycle.engine.asyncio.wait_for", AsyncMock(side_effect=asyncio.TimeoutError)):
            run(engine.run(trade))

        engine._lifecycle_repo.release_claim.assert_awaited_once_with(trade.id)
        engine._lifecycle_repo.mark_needs_reconciliation.assert_not_awaited()

    def test_exception_in_pipeline_marks_failed(self):
        """A non-recoverable exception in the pipeline causes mark_failed to be called."""
        engine = _make_engine()
        # Raising in release_claim (called at the end of HOLD/UPDATE_PNL) is non-recoverable
        engine._lifecycle_repo.update_trade = AsyncMock(
            side_effect=RuntimeError("DB write failed")
        )
        # A trade with no SL/TP/trailing → UPDATE_PNL → update_trade raises → mark_failed
        trade = make_trade(mode="paper", stop_loss=None, take_profit=None)
        run(engine.run(trade))
        engine._lifecycle_repo.mark_failed.assert_awaited()

    def test_exception_does_not_propagate(self):
        """engine.run() must never raise — catch everything."""
        engine = _make_engine()
        engine._lifecycle_repo.update_trade = AsyncMock(
            side_effect=RuntimeError("catastrophic DB failure")
        )
        trade = make_trade(mode="paper", stop_loss=None, take_profit=None)
        # Must not raise
        run(engine.run(trade))


def test_max_retry_failures_are_recoverable_for_open_trades():
    assert _is_transient_lifecycle_error("max retries exceeded (6 > 5)")


@pytest.mark.parametrize(
    "error",
    [
        "<ConnectionTerminated error_code:1, last_stream_id:71, additional_data:None>",
        "<StreamReset stream_id:175, error_code:5, remote_reset:True>",
        "StreamIDTooLowError: 149 is lower than 149",
        "{'message': 'JSON could not be generated', 'details': 'cloudflare 400 Bad Request'}",
        "deque mutated during iteration",
        "dictionary keys changed during iteration",
        "Invalid input ConnectionInputs.RECV_HEADERS in state ConnectionState.CLOSED",
        "Invalid input StreamInputs.SEND_HEADERS in state 5",
        "Received pseudo-header in trailer {b':method', b':authority', b':scheme', b':path'}",
        "175",
    ],
)
def test_observed_infrastructure_failures_are_recoverable(error):
    assert _is_transient_lifecycle_error(error)
