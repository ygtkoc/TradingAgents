"""
Shared pytest fixtures for the Execution Engine test suite.

All fixtures use in-memory / mock objects — no real DB, no real exchange API.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

# Inject required env vars before any module-level settings are evaluated
_TEST_ENV = {
    "SUPABASE_URL": "https://test.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-role-key",
    "API_KEY_ENCRYPTION_SECRET": "test-encryption-secret-32-chars!!",
}
for _k, _v in _TEST_ENV.items():
    os.environ.setdefault(_k, _v)

from src.db.models import (
    Bot,
    BotConfig,
    ExchangeAccount,
    MarketSnapshot,
    Trade,
    TradeDecision,
    TradeStatus,
    UserSettings,
)


# ── Time helpers ──────────────────────────────────────────────────────────────

def utcnow_str() -> str:
    return datetime.now(timezone.utc).isoformat()


def minutes_ago_str(minutes: int) -> str:
    from datetime import timedelta
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


# ── Model factories ───────────────────────────────────────────────────────────

def make_decision(
    *,
    mode: str = "paper",
    final_decision: str = "open_long",
    approval_status: str = "auto_approved",
    symbol: str = "BTC/USDT",
    direction: str = "long",
    exchange: str = "binance",
    agent_run_id: str = "run-abc123",
    execution_status: str = "executing",
    linked_trade_id: Optional[str] = None,
    security_summary: Optional[dict] = None,
    veto_summary: Optional[dict] = None,
    risk_summary: Optional[dict] = None,
    created_at: Optional[str] = None,
    **kwargs: Any,
) -> TradeDecision:
    return TradeDecision(
        id="decision-001",
        user_id="user-001",
        bot_id="bot-001",
        agent_run_id=agent_run_id,
        signal_id="signal-001",
        exchange=exchange,
        symbol=symbol,
        direction=direction,
        mode=mode,
        final_decision=final_decision,
        approval_status=approval_status,
        security_summary=security_summary or {},
        veto_summary=veto_summary or {},
        risk_summary=risk_summary or {
            "entry_price": 50000.0,
            "quantity": 0.01,
            "stop_loss": 48000.0,
            "take_profit": 54000.0,
        },
        execution_status=execution_status,
        linked_trade_id=linked_trade_id,
        created_at=created_at or utcnow_str(),
        **kwargs,
    )


def make_bot(
    *,
    status: str = "active",
    mode: str = "paper",
    real_trading_enabled: bool = False,
    max_open_positions: int = 5,
    max_position_size_pct: float = 10.0,
    risk_per_trade_pct: float = 2.0,
    max_daily_loss_pct: float = 5.0,
    trading_pairs: Optional[list] = None,
    exchange_account_id: Optional[str] = "account-001",
    **kwargs: Any,
) -> Bot:
    return Bot(
        id="bot-001",
        user_id="user-001",
        name="Test Bot",
        status=status,
        mode=mode,
        real_trading_enabled=real_trading_enabled,
        requires_manual_approval=False,
        max_open_positions=max_open_positions,
        max_position_size_pct=max_position_size_pct,
        risk_per_trade_pct=risk_per_trade_pct,
        max_daily_loss_pct=max_daily_loss_pct,
        base_currency="USDT",
        trading_pairs=trading_pairs or ["BTC/USDT", "ETH/USDT"],
        active_config_id=None,
        exchange_account_id=exchange_account_id,
        **kwargs,
    )


def make_user_settings(
    *,
    trading_enabled: bool = True,
    real_trading_enabled: bool = False,
    real_trading_allowed: bool = False,
    daily_loss_limit_usd: Optional[float] = None,
    max_concurrent_trades: Optional[int] = None,
    **kwargs: Any,
) -> UserSettings:
    return UserSettings(
        user_id="user-001",
        trading_enabled=trading_enabled,
        real_trading_enabled=real_trading_enabled,
        real_trading_allowed=real_trading_allowed,
        real_trading_requires_approval=True,
        daily_loss_limit_usd=daily_loss_limit_usd,
        max_concurrent_trades=max_concurrent_trades,
        **kwargs,
    )


def make_exchange_account(
    *,
    is_active: bool = True,
    can_trade: bool = True,
    can_withdraw: bool = False,
    withdrawal_detected: bool = False,
    encrypted_api_key: Optional[str] = "deadbeef" * 4,
    encrypted_api_secret: Optional[str] = "cafebabe" * 4,
    key_iv: Optional[str] = "aabbcc" * 2,
    **kwargs: Any,
) -> ExchangeAccount:
    return ExchangeAccount(
        id="account-001",
        user_id="user-001",
        bot_id="bot-001",
        exchange="binance",
        label="Test Account",
        is_active=is_active,
        can_trade=can_trade,
        can_withdraw=can_withdraw,
        withdrawal_detected=withdrawal_detected,
        encrypted_api_key=encrypted_api_key,
        encrypted_api_secret=encrypted_api_secret,
        key_iv=key_iv,
        **kwargs,
    )


def make_market_snapshot(
    *,
    close_price: float = 50_000.0,
    spread_pct: Optional[float] = 0.1,
    **kwargs: Any,
) -> MarketSnapshot:
    return MarketSnapshot(
        id="snap-001",
        exchange="binance",
        symbol="BTC/USDT",
        timeframe="1h",
        close_price=close_price,
        high_price=close_price * 1.01,
        low_price=close_price * 0.99,
        open_price=close_price * 0.995,
        volume=1000.0,
        spread_pct=spread_pct,
        captured_at=utcnow_str(),
        **kwargs,
    )


def make_trade(
    *,
    trade_decision_id: str = "decision-001",
    mode: str = "paper",
    status: str = TradeStatus.SIMULATED.value,
    entry_price: float = 50_000.0,
    quantity: float = 0.01,
    **kwargs: Any,
) -> Trade:
    return Trade(
        id="trade-001",
        user_id="user-001",
        bot_id="bot-001",
        trade_decision_id=trade_decision_id,
        agent_run_id="run-abc123",
        exchange="binance",
        symbol="BTC/USDT",
        side="buy",
        direction="long",
        mode=mode,
        status=status,
        entry_price=entry_price,
        quantity=quantity,
        stop_loss=48_000.0,
        take_profit=54_000.0,
        exchange_order_id="mock-order-001",
        filled_quantity=quantity,
        avg_fill_price=entry_price,
        created_at=utcnow_str(),
        **kwargs,
    )


# ── Pytest fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def decision():
    return make_decision()

@pytest.fixture
def live_decision():
    return make_decision(mode="live", final_decision="open_long", approval_status="approved")

@pytest.fixture
def bot():
    return make_bot()

@pytest.fixture
def live_bot():
    return make_bot(mode="live", real_trading_enabled=True)

@pytest.fixture
def user_settings():
    return make_user_settings()

@pytest.fixture
def live_user_settings():
    return make_user_settings(
        real_trading_enabled=True,
        real_trading_allowed=True,
        trading_enabled=True,
    )

@pytest.fixture
def exchange_account():
    return make_exchange_account()

@pytest.fixture
def market_snapshot():
    return make_market_snapshot()

@pytest.fixture
def trade():
    return make_trade()
