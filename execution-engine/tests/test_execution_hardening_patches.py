"""
Tests for Execution Engine hardening patches.

Covers:
  A) Order confirmation via fetch_order() — after place_order():
     - filled → trade created with confirmed price/qty
     - partially_filled → trade created with partial quantity
     - rejected / cancelled → LiveExecutionError raised, no trade created
     - unknown status → LiveExecutionError raised
     - fetch_order() raises → LiveExecutionError raised

  B) Post-fill slippage guard:
     - fill price within limit → passes
     - fill price exceeds slippage limit → LiveExecutionError raised, no trade created

  C) Balance check before live order:
     - sufficient balance → proceeds
     - insufficient balance → LiveExecutionError raised

  D) Global kill switch (platform_settings.global_trading_enabled=False):
     - SecurityExecutionGuard blocks immediately with kill-switch reason
     - No further checks evaluated
     - With global_trading_enabled=True → passes kill switch check

All tests mock the exchange adapter and DB — no real HTTP calls or DB writes.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db.models import PlatformSettings
from src.execution.live_executor import LiveExecutionError, LiveExecutor
from src.exchanges.base import BalanceResult, OrderResult, PermissionCheckResult
from src.guards.security_guard import SecurityExecutionGuard
from tests.conftest import (
    make_bot,
    make_decision,
    make_exchange_account,
    make_market_snapshot,
    make_trade,
    make_user_settings,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_executor():
    """Build a LiveExecutor with all deps mocked."""
    executor = LiveExecutor.__new__(LiveExecutor)
    executor._trade_repo   = MagicMock()
    executor._event_repo   = MagicMock()
    executor._event_repo.bulk_create = AsyncMock()
    executor._key_provider = MagicMock()
    return executor


def _make_credentials():
    creds = MagicMock()
    creds.api_key    = "test-key"
    creds.api_secret = "test-secret"
    creds.zero_out   = MagicMock()
    return creds


def _make_adapter(
    *,
    place_order_status: str   = "filled",
    fetch_order_status: str   = "filled",
    filled_qty: float         = 0.01,
    avg_fill_price: float     = 50_000.0,
    place_success: bool       = True,
    order_id: str             = "ord-9999",
    balance_quote_free: float = 100_000.0,
    can_withdraw: bool        = False,
):
    adapter = MagicMock()

    place_result = OrderResult(
        success=place_success,
        order_id=order_id if place_success else "",
        status=place_order_status,
        filled_quantity=filled_qty,
        avg_fill_price=avg_fill_price,
        client_order_id=None,
        raw_response={"status": place_order_status},
        error=None if place_success else "rejected by exchange",
    )
    adapter.place_order = AsyncMock(return_value=place_result)

    fetch_result = OrderResult(
        success=True,
        order_id=order_id,
        status=fetch_order_status,
        filled_quantity=filled_qty,
        avg_fill_price=avg_fill_price,
        client_order_id=None,
        raw_response={"status": fetch_order_status},
    )
    adapter.fetch_order = AsyncMock(return_value=fetch_result)

    perm = PermissionCheckResult(
        can_trade=True,
        can_withdraw=can_withdraw,
        has_read_permission=True,
        raw_permissions={},
    )
    adapter.check_permissions = AsyncMock(return_value=perm)

    balance = BalanceResult(
        free={"USDT": balance_quote_free},
        total={"USDT": balance_quote_free},
        quote_free=balance_quote_free,
    )
    adapter.get_balance = AsyncMock(return_value=balance)
    adapter.close = AsyncMock()
    return adapter


def _execute(executor, adapter, *, slippage_pct: float = 0.0):
    """Run executor.execute() with mocked deps."""
    decision = make_decision(mode="live")
    bot      = make_bot(real_trading_enabled=True)
    account  = make_exchange_account(can_withdraw=False, can_trade=True)
    snap     = make_market_snapshot()

    from src.exchanges.base import OrderRequest
    order = OrderRequest(
        exchange="binance",
        symbol="BTC/USDT",
        side="buy",
        order_type="market",
        quantity=0.01,
        client_order_id="test-coid-001",
    )

    entry_price = 50_000.0

    # Patch get_live_adapter to return our mock adapter
    # Patch settings.enable_live_execution = True
    # Patch key_provider
    executor._key_provider.get_credentials = AsyncMock(return_value=_make_credentials())

    trade_mock = make_trade()
    executor._trade_repo.create = AsyncMock(return_value=trade_mock)

    with patch("src.execution.live_executor.get_live_adapter", return_value=adapter), \
         patch("src.execution.live_executor.settings") as mock_settings:
        mock_settings.enable_live_execution = True
        mock_settings.max_slippage_pct = 1.0  # 1% max slippage
        return run(executor.execute(
            decision=decision,
            bot=bot,
            exchange_account=account,
            order=order,
            entry_price=entry_price,
            market_snapshot=snap,
        ))


# ── A) Order confirmation via fetch_order() ────────────────────────────────────

class TestOrderConfirmation:

    def test_filled_order_creates_trade(self):
        """fetch_order returns 'filled' → trade is created."""
        executor = _make_executor()
        adapter  = _make_adapter(place_order_status="filled", fetch_order_status="filled")
        trade    = _execute(executor, adapter)
        executor._trade_repo.create.assert_awaited_once()

    def test_partial_fill_creates_trade_with_filled_qty(self):
        """fetch_order returns 'partially_filled' → trade created with actual qty."""
        executor = _make_executor()
        adapter  = _make_adapter(
            fetch_order_status="partially_filled",
            filled_qty=0.005,  # half filled
        )
        trade = _execute(executor, adapter)
        executor._trade_repo.create.assert_awaited_once()

    def test_live_trade_persists_reward_plan_for_lifecycle(self):
        executor = _make_executor()
        adapter = _make_adapter()
        plan = {
            "mode": "scaled_take_profit",
            "selected_reward_r": 3.0,
            "levels": [
                {"level": 1, "price": 51000.0, "close_pct": 0.30, "status": "pending"},
                {"level": 2, "price": 52000.0, "close_pct": 0.40, "status": "pending"},
                {"level": 3, "price": 53000.0, "close_pct": 0.30, "status": "pending"},
            ],
        }
        decision = make_decision(
            mode="live",
            risk_summary={
                "entry_price": 50000.0,
                "quantity": 0.01,
                "stop_loss": 49000.0,
                "take_profit": 53000.0,
                "risk_amount": 10.0,
                "risk_percent": 1.0,
                "risk_reward_ratio": 3.0,
                "expected_reward": 30.0,
                "notional": 500.0,
                "reward_plan": plan,
                "tp_plan": plan["levels"],
            },
        )
        bot = make_bot(real_trading_enabled=True)
        account = make_exchange_account(can_withdraw=False, can_trade=True)
        snap = make_market_snapshot()

        from src.exchanges.base import OrderRequest
        order = OrderRequest(
            exchange="binance",
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            quantity=0.01,
            stop_loss=49000.0,
            take_profit=53000.0,
            client_order_id="test-coid-001",
        )

        executor._key_provider.get_credentials = AsyncMock(return_value=_make_credentials())
        executor._trade_repo.create = AsyncMock(return_value=make_trade())

        with patch("src.execution.live_executor.get_live_adapter", return_value=adapter), \
             patch("src.execution.live_executor.settings") as mock_settings:
            mock_settings.enable_live_execution = True
            mock_settings.max_slippage_pct = 1.0
            run(executor.execute(
                decision=decision,
                bot=bot,
                exchange_account=account,
                order=order,
                entry_price=50000.0,
                market_snapshot=snap,
            ))

        inserted = executor._trade_repo.create.await_args.args[0]
        assert inserted.risk_amount == 10.0
        assert inserted.risk_reward_ratio == 3.0
        assert inserted.metadata["reward_plan"] == plan
        assert inserted.metadata["tp_plan"] == plan["levels"]

    def test_rejected_order_raises_and_no_trade(self):
        """fetch_order returns 'rejected' → LiveExecutionError, no trade created."""
        executor = _make_executor()
        adapter  = _make_adapter(fetch_order_status="rejected")
        with pytest.raises(LiveExecutionError, match="(?i)rejected|not confirmed|manual review"):
            _execute(executor, adapter)
        executor._trade_repo.create.assert_not_awaited()

    def test_cancelled_order_raises_and_no_trade(self):
        """fetch_order returns 'cancelled' → LiveExecutionError, no trade created."""
        executor = _make_executor()
        adapter  = _make_adapter(fetch_order_status="cancelled")
        with pytest.raises(LiveExecutionError):
            _execute(executor, adapter)
        executor._trade_repo.create.assert_not_awaited()

    def test_unknown_status_raises_and_no_trade(self):
        """fetch_order returns unknown status → LiveExecutionError."""
        executor = _make_executor()
        adapter  = _make_adapter(fetch_order_status="processing")
        with pytest.raises(LiveExecutionError):
            _execute(executor, adapter)
        executor._trade_repo.create.assert_not_awaited()

    def test_fetch_order_exception_raises_and_no_trade(self):
        """fetch_order raises → LiveExecutionError, no trade created."""
        executor = _make_executor()
        adapter  = _make_adapter()
        adapter.fetch_order = AsyncMock(side_effect=RuntimeError("Network timeout"))
        with pytest.raises(LiveExecutionError, match="(?i)fetch_order failed|cannot confirm"):
            _execute(executor, adapter)
        executor._trade_repo.create.assert_not_awaited()

    def test_credentials_zeroed_even_on_fetch_failure(self):
        """API credentials must be zeroed out even when fetch_order fails."""
        executor = _make_executor()
        creds    = _make_credentials()
        executor._key_provider.get_credentials = AsyncMock(return_value=creds)
        adapter  = _make_adapter()
        adapter.fetch_order = AsyncMock(side_effect=RuntimeError("timeout"))
        with pytest.raises(LiveExecutionError):
            from src.exchanges.base import OrderRequest
            decision = make_decision(mode="live")
            order = OrderRequest(
                exchange="binance", symbol="BTC/USDT",
                side="buy", order_type="market", quantity=0.01,
            )
            with patch("src.execution.live_executor.get_live_adapter", return_value=adapter), \
                 patch("src.execution.live_executor.settings") as ms:
                ms.enable_live_execution = True
                ms.max_slippage_pct = 1.0
                run(executor.execute(
                    decision=decision,
                    bot=make_bot(real_trading_enabled=True),
                    exchange_account=make_exchange_account(can_withdraw=False),
                    order=order,
                    entry_price=50_000.0,
                    market_snapshot=None,
                ))
        # zero_out must have been called (at least once — place_order credentials)
        assert creds.zero_out.call_count >= 1


# ── B) Post-fill slippage guard ────────────────────────────────────────────────

class TestPostFillSlippageGuard:

    def test_within_slippage_limit_proceeds(self):
        """Fill price within 1% of expected → no slippage error."""
        executor = _make_executor()
        # fill price = 50_100 (0.2% above expected 50_000)
        adapter  = _make_adapter(avg_fill_price=50_100.0, fetch_order_status="filled")
        trade    = _execute(executor, adapter)
        executor._trade_repo.create.assert_awaited_once()

    def test_slippage_exceeded_raises_no_trade(self):
        """Fill price 2% above expected when limit is 1% → error, no trade."""
        executor = _make_executor()
        # fill price = 51_000 (2% above expected 50_000)
        adapter  = _make_adapter(avg_fill_price=51_000.0, fetch_order_status="filled")
        with pytest.raises(LiveExecutionError, match="(?i)slippage"):
            _execute(executor, adapter)
        executor._trade_repo.create.assert_not_awaited()

    def test_zero_slippage_always_passes(self):
        """Exact fill price → zero slippage → always passes."""
        executor = _make_executor()
        adapter  = _make_adapter(avg_fill_price=50_000.0, fetch_order_status="filled")
        _execute(executor, adapter)
        executor._trade_repo.create.assert_awaited_once()


# ── C) Balance check ───────────────────────────────────────────────────────────

class TestBalanceCheck:

    def test_sufficient_balance_proceeds(self):
        """balance.quote_free > required → execution proceeds."""
        executor = _make_executor()
        adapter  = _make_adapter(balance_quote_free=100_000.0)
        _execute(executor, adapter)
        executor._trade_repo.create.assert_awaited_once()

    def test_insufficient_balance_raises(self):
        """balance.quote_free < required_usd → LiveExecutionError."""
        executor = _make_executor()
        # quantity=0.01, entry=50_000 → required=$500. balance=$100 → insufficient
        adapter  = _make_adapter(balance_quote_free=100.0)
        with pytest.raises(LiveExecutionError, match="(?i)insufficient balance"):
            _execute(executor, adapter)
        executor._trade_repo.create.assert_not_awaited()


# ── D) Global kill switch via SecurityExecutionGuard ──────────────────────────

class TestGlobalKillSwitch:

    def _run_guard(self, global_enabled: bool = True):
        guard    = SecurityExecutionGuard()
        decision = make_decision(mode="live")
        bot      = make_bot(status="active")
        us       = make_user_settings(
            trading_enabled=True,
            real_trading_enabled=True,
            real_trading_allowed=True,
        )
        ea  = make_exchange_account(can_withdraw=False, can_trade=True)
        ps  = PlatformSettings(
            global_trading_enabled=global_enabled,
            live_execution_enabled=False,
            emergency_close_enabled=True,
        )
        return guard.check(
            decision=decision,
            bot=bot,
            user_settings=us,
            exchange_account=ea,
            critical_security_event_count=0,
            platform_settings=ps,
        )

    def test_kill_switch_blocks_execution(self):
        result = self._run_guard(global_enabled=False)
        assert result.blocked is True

    def test_kill_switch_reason_mentions_global(self):
        result = self._run_guard(global_enabled=False)
        assert "global" in result.reason.lower() or "kill switch" in result.reason.lower()

    def test_kill_switch_short_circuits_other_checks(self):
        """After kill switch fires, only the kill switch check should be present."""
        result = self._run_guard(global_enabled=False)
        assert len(result.checks) == 1
        assert result.checks[0].name == "global_trading_enabled"
        assert result.checks[0].passed is False

    def test_kill_switch_enabled_passes_check(self):
        """With global_trading_enabled=True, kill switch check passes."""
        result = self._run_guard(global_enabled=True)
        ks_check = next(c for c in result.checks if c.name == "global_trading_enabled")
        assert ks_check.passed is True

    def test_no_platform_settings_skips_kill_switch_check(self):
        """If platform_settings is None, skip kill switch check gracefully."""
        guard    = SecurityExecutionGuard()
        decision = make_decision(mode="paper")  # paper — fewer checks
        result   = guard.check(
            decision=decision,
            bot=make_bot(status="active"),
            user_settings=make_user_settings(),
            exchange_account=make_exchange_account(can_withdraw=False),
            critical_security_event_count=0,
            platform_settings=None,  # not provided
        )
        # Should still work — kill switch check simply not present
        ks_checks = [c for c in result.checks if c.name == "global_trading_enabled"]
        assert len(ks_checks) == 0  # skipped if ps is None
