"""
Shared test fixtures for the Position Engine test suite.

Factories produce typed model instances without any DB access.
All factories accept keyword overrides so tests can mutate specific fields.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

# ── Inject required env vars before any module-level settings are evaluated ───
# This allows tests to run without a real .env file or Supabase connection.
_TEST_ENV = {
    "SUPABASE_URL": "https://test.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-role-key",
    "API_KEY_ENCRYPTION_SECRET": "test-encryption-secret-32-chars!!",
}
for _k, _v in _TEST_ENV.items():
    os.environ.setdefault(_k, _v)

from src.db.models import (
    Bot,
    ExchangeAccount,
    MarketSnapshot,
    PlatformSettings,
    Trade,
    UserSettings,
)
from src.exchanges.base import BalanceResult, OrderResult, PermissionCheckResult


# ── Helpers ────────────────────────────────────────────────────────────────────

def _trade_id()    -> str: return "trade-aaaabbbb-0001"
def _bot_id()      -> str: return "bot-ccccdddd-0001"
def _user_id()     -> str: return "user-eeeeffff-0001"
def _account_id()  -> str: return "acct-gggghhhh-0001"
def _snapshot_id() -> str: return "snap-iiiijjjj-0001"


# ── Trade factory ──────────────────────────────────────────────────────────────

def make_trade(
    *,
    id: str                       = _trade_id(),
    user_id: str                  = _user_id(),
    bot_id: str                   = _bot_id(),
    trade_decision_id: str        = "td-00000001",
    exchange: str                 = "binance",
    symbol: str                   = "BTC/USDT",
    side: str                     = "buy",
    direction: str                = "long",
    mode: str                     = "paper",
    status: str                   = "open",
    entry_price: float            = 50_000.0,
    quantity: float               = 0.1,
    stop_loss: Optional[float]    = None,
    take_profit: Optional[float]  = None,
    filled_quantity: Optional[float] = None,
    avg_fill_price: Optional[float]  = None,
    lifecycle_status: str         = "idle",
    lifecycle_worker_id: Optional[str] = None,
    trailing_stop_price: Optional[float] = None,
    highest_price_seen: Optional[float]  = None,
    lowest_price_seen: Optional[float]   = None,
    exchange_order_id: Optional[str]     = None,
    unrealized_pnl: Optional[float]      = None,
    realized_pnl: Optional[float]        = None,
    risk_amount: Optional[float]         = None,
    risk_percent: Optional[float]        = None,
    risk_reward_ratio: Optional[float]   = None,
    expected_reward: Optional[float]     = None,
    pnl_pct: Optional[float]             = None,
    r_multiple: Optional[float]          = None,
    metadata: Optional[dict]             = None,
    created_at: str               = "2025-01-01T00:00:00+00:00",
    **kwargs: Any,
) -> Trade:
    return Trade(
        id=id,
        user_id=user_id,
        bot_id=bot_id,
        trade_decision_id=trade_decision_id,
        exchange=exchange,
        symbol=symbol,
        side=side,
        direction=direction,
        mode=mode,
        status=status,
        entry_price=entry_price,
        quantity=quantity,
        stop_loss=stop_loss,
        take_profit=take_profit,
        filled_quantity=filled_quantity,
        avg_fill_price=avg_fill_price,
        lifecycle_status=lifecycle_status,
        lifecycle_worker_id=lifecycle_worker_id,
        trailing_stop_price=trailing_stop_price,
        highest_price_seen=highest_price_seen,
        lowest_price_seen=lowest_price_seen,
        exchange_order_id=exchange_order_id,
        unrealized_pnl=unrealized_pnl,
        realized_pnl=realized_pnl,
        risk_amount=risk_amount,
        risk_percent=risk_percent,
        risk_reward_ratio=risk_reward_ratio,
        expected_reward=expected_reward,
        pnl_pct=pnl_pct,
        r_multiple=r_multiple,
        metadata=metadata or {},
        created_at=created_at,
    )


def make_short_trade(**kwargs) -> Trade:
    """Convenience: make a live short trade."""
    defaults = dict(direction="short", side="sell", mode="live")
    defaults.update(kwargs)
    return make_trade(**defaults)


def make_live_trade(**kwargs) -> Trade:
    """Convenience: make a live long trade."""
    defaults = dict(mode="live", direction="long")
    defaults.update(kwargs)
    return make_trade(**defaults)


# ── Bot factory ────────────────────────────────────────────────────────────────

def make_bot(
    *,
    id: str                     = _bot_id(),
    user_id: str                = _user_id(),
    name: str                   = "TestBot",
    status: str                 = "active",
    mode: str                   = "paper",
    real_trading_enabled: bool  = False,
    exchange_account_id: Optional[str] = _account_id(),
    trailing_stop_pct: Optional[float] = None,
    is_archived: bool           = False,
    **kwargs: Any,
) -> Bot:
    return Bot(
        id=id,
        user_id=user_id,
        name=name,
        status=status,
        mode=mode,
        real_trading_enabled=real_trading_enabled,
        exchange_account_id=exchange_account_id,
        trailing_stop_pct=trailing_stop_pct,
        is_archived=is_archived,
    )


# ── UserSettings factory ───────────────────────────────────────────────────────

def make_user_settings(
    *,
    user_id: str            = _user_id(),
    trading_enabled: bool   = True,
    real_trading_enabled: bool = False,
    real_trading_allowed: bool = False,
    **kwargs: Any,
) -> UserSettings:
    return UserSettings(
        user_id=user_id,
        trading_enabled=trading_enabled,
        real_trading_enabled=real_trading_enabled,
        real_trading_allowed=real_trading_allowed,
    )


# ── ExchangeAccount factory ────────────────────────────────────────────────────

def make_exchange_account(
    *,
    id: str                      = _account_id(),
    user_id: str                 = _user_id(),
    exchange: str                = "binance",
    is_active: bool              = True,
    can_trade: bool              = True,
    can_withdraw: bool           = False,
    withdrawal_detected: bool    = False,
    encrypted_api_key: str       = "encrypted-key",
    encrypted_api_secret: str    = "encrypted-secret",
    key_iv: str                  = "some-iv",
    **kwargs: Any,
) -> ExchangeAccount:
    return ExchangeAccount(
        id=id,
        user_id=user_id,
        exchange=exchange,
        is_active=is_active,
        can_trade=can_trade,
        can_withdraw=can_withdraw,
        withdrawal_detected=withdrawal_detected,
        encrypted_api_key=encrypted_api_key,
        encrypted_api_secret=encrypted_api_secret,
        key_iv=key_iv,
    )


# ── MarketSnapshot factory ─────────────────────────────────────────────────────

def make_snapshot(
    *,
    exchange: str   = "binance",
    symbol: str     = "BTC/USDT",
    close_price: float = 50_000.0,
    high_price: float  = 51_000.0,
    low_price: float   = 49_000.0,
    open_price: float  = 49_500.0,
    volume: float      = 1_000.0,
    spread_pct: float  = 0.05,
    **kwargs: Any,
) -> MarketSnapshot:
    return MarketSnapshot(
        id=_snapshot_id(),
        exchange=exchange,
        symbol=symbol,
        timeframe="1h",
        close_price=close_price,
        high_price=high_price,
        low_price=low_price,
        open_price=open_price,
        volume=volume,
        spread_pct=spread_pct,
        captured_at="2025-01-01T00:00:00+00:00",
    )


# ── PlatformSettings factory ───────────────────────────────────────────────────

def make_platform_settings(
    *,
    global_trading_enabled: bool   = True,
    live_execution_enabled: bool   = False,
    emergency_close_enabled: bool  = True,
    max_allowed_slippage_pct: float = 1.0,
) -> PlatformSettings:
    return PlatformSettings(
        global_trading_enabled=global_trading_enabled,
        live_execution_enabled=live_execution_enabled,
        emergency_close_enabled=emergency_close_enabled,
        max_allowed_slippage_pct=max_allowed_slippage_pct,
    )


# ── Mock exchange adapter factory ──────────────────────────────────────────────

def make_mock_adapter(
    *,
    fetch_order_status: str    = "filled",
    filled_quantity: float     = 0.1,
    avg_fill_price: float      = 50_000.0,
    place_order_success: bool  = True,
    order_id: str              = "order-12345",
) -> MagicMock:
    adapter = MagicMock()

    # fetch_order
    order_result = OrderResult(
        success=True,
        order_id=order_id,
        status=fetch_order_status,
        filled_quantity=filled_quantity,
        avg_fill_price=avg_fill_price,
        raw_response={"status": fetch_order_status},
    )
    adapter.fetch_order = AsyncMock(return_value=order_result)

    # place_order
    place_result = OrderResult(
        success=place_order_success,
        order_id=order_id if place_order_success else None,
        status="filled" if place_order_success else "rejected",
        filled_quantity=filled_quantity if place_order_success else None,
        avg_fill_price=avg_fill_price if place_order_success else None,
        raw_response={"status": "filled" if place_order_success else "rejected"},
    )
    adapter.place_order = AsyncMock(return_value=place_result)

    # check_permissions
    perm = PermissionCheckResult(
        can_trade=True, can_withdraw=False,
        has_read_permission=True, raw_permissions={},
    )
    adapter.check_permissions = AsyncMock(return_value=perm)

    # get_balance
    balance = BalanceResult(free={"USDT": 100_000.0}, total={"USDT": 100_000.0}, quote_free=100_000.0)
    adapter.get_balance = AsyncMock(return_value=balance)

    # close
    adapter.close = AsyncMock()

    return adapter


# ── Async runner helper ────────────────────────────────────────────────────────

def run(coro):
    """Run a coroutine synchronously (for use in pytest without async plugin)."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ── pytest fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def long_trade():
    return make_trade(direction="long", mode="paper")

@pytest.fixture
def short_trade():
    return make_trade(direction="short", side="sell", mode="paper")

@pytest.fixture
def live_long_trade():
    return make_trade(direction="long", mode="live")

@pytest.fixture
def platform_settings():
    return make_platform_settings()

@pytest.fixture
def active_bot():
    return make_bot(status="active")

@pytest.fixture
def safe_exchange_account():
    return make_exchange_account(can_withdraw=False, can_trade=True, is_active=True)
