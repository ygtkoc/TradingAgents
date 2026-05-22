"""
Tests for RiskExecutionGuard.

All checks must fail-closed: any violation → blocked=True.
"""
from __future__ import annotations

import pytest

from src.guards.risk_guard import RiskExecutionGuard
from tests.conftest import (
    make_bot,
    make_decision,
    make_market_snapshot,
    make_user_settings,
)

PORTFOLIO = 10_000.0
ENTRY     = 50_000.0
QUANTITY  = 0.01   # $500 position → 5% of portfolio


_MISSING = object()


def _run(
    decision=_MISSING,
    bot=_MISSING,
    user_settings=_MISSING,
    open_trade_count=0,
    market_snapshot=_MISSING,
    portfolio_value_usd=PORTFOLIO,
    daily_loss_usd=0.0,
    quantity=QUANTITY,
    entry_price=ENTRY,
):
    guard = RiskExecutionGuard()
    return guard.check(
        decision=decision if decision is not _MISSING else make_decision(),
        bot=bot if bot is not _MISSING else make_bot(),
        user_settings=user_settings if user_settings is not _MISSING else make_user_settings(),
        open_trade_count=open_trade_count,
        market_snapshot=market_snapshot if market_snapshot is not _MISSING else make_market_snapshot(close_price=ENTRY),
        portfolio_value_usd=portfolio_value_usd,
        daily_loss_usd=daily_loss_usd,
        quantity=quantity,
        entry_price=entry_price,
    )


class TestSymbolAllowed:
    def test_symbol_in_allowed_list_passes(self):
        bot = make_bot(trading_pairs=["BTC/USDT"])
        result = _run(bot=bot)
        check = next(c for c in result.checks if c.name == "symbol_allowed")
        assert check.passed

    def test_symbol_not_in_list_blocks(self):
        bot = make_bot(trading_pairs=["ETH/USDT"])
        result = _run(bot=bot)
        check = next(c for c in result.checks if c.name == "symbol_allowed")
        assert not check.passed
        assert result.blocked

    def test_empty_trading_pairs_allows_all(self):
        bot = make_bot(trading_pairs=[])
        result = _run(bot=bot)
        check = next(c for c in result.checks if c.name == "symbol_allowed")
        assert check.passed


class TestMaxConcurrentTrades:
    def test_under_limit_passes(self):
        us = make_user_settings(max_concurrent_trades=5)
        result = _run(open_trade_count=2, user_settings=us)
        check = next(c for c in result.checks if c.name == "max_concurrent_trades")
        assert check.passed

    def test_at_limit_blocks(self):
        us = make_user_settings(max_concurrent_trades=3)
        result = _run(open_trade_count=3, user_settings=us)
        check = next(c for c in result.checks if c.name == "max_concurrent_trades")
        assert not check.passed
        assert result.blocked

    def test_no_limit_set_always_passes(self):
        us = make_user_settings(max_concurrent_trades=None)
        result = _run(open_trade_count=99, user_settings=us)
        check = next(c for c in result.checks if c.name == "max_concurrent_trades")
        assert check.passed


class TestMaxPositionsPerBot:
    def test_under_bot_limit_passes(self):
        bot = make_bot(max_open_positions=5)
        result = _run(bot=bot, open_trade_count=2)
        check = next(c for c in result.checks if c.name == "max_positions_per_bot")
        assert check.passed

    def test_at_bot_limit_blocks(self):
        bot = make_bot(max_open_positions=3)
        result = _run(bot=bot, open_trade_count=3)
        check = next(c for c in result.checks if c.name == "max_positions_per_bot")
        assert not check.passed
        assert result.blocked


class TestDailyLossLimit:
    def test_no_loss_passes(self):
        result = _run(daily_loss_usd=0.0)
        check = next(c for c in result.checks if c.name == "daily_loss_limit")
        assert check.passed

    def test_user_usd_limit_triggers_block(self):
        us = make_user_settings(daily_loss_limit_usd=100.0)
        result = _run(daily_loss_usd=150.0, user_settings=us)
        check = next(c for c in result.checks if c.name == "daily_loss_limit")
        assert not check.passed
        assert result.blocked

    def test_bot_pct_limit_triggers_block(self):
        bot = make_bot(max_daily_loss_pct=5.0)
        # $600 loss on $10k portfolio = 6%
        result = _run(bot=bot, daily_loss_usd=600.0, portfolio_value_usd=PORTFOLIO)
        check = next(c for c in result.checks if c.name == "daily_loss_limit")
        assert not check.passed
        assert result.blocked

    def test_within_pct_limit_passes(self):
        bot = make_bot(max_daily_loss_pct=5.0)
        result = _run(bot=bot, daily_loss_usd=400.0, portfolio_value_usd=PORTFOLIO)
        check = next(c for c in result.checks if c.name == "daily_loss_limit")
        assert check.passed


class TestPositionSize:
    def test_position_within_limit_passes(self):
        # $500 / $10,000 = 5% → within 10% limit
        bot = make_bot(max_position_size_pct=10.0)
        result = _run(bot=bot, quantity=0.01, entry_price=50_000.0)
        check = next(c for c in result.checks if c.name == "position_size_pct")
        assert check.passed

    def test_wallet_risk_sizing_allows_large_notional_when_risk_is_bounded(self):
        # $500 / $1,000 = 50% notional is allowed when stop-loss risk remains bounded.
        bot = make_bot(max_position_size_pct=10.0)
        result = _run(bot=bot, quantity=0.01, entry_price=50_000.0, portfolio_value_usd=1_000.0)
        check = next(c for c in result.checks if c.name == "position_size_pct")
        assert check.passed
        assert result.blocked

    def test_zero_portfolio_blocks(self):
        result = _run(portfolio_value_usd=0.0)
        check = next(c for c in result.checks if c.name == "position_size_pct")
        assert not check.passed

    def test_futures_profile_allows_full_notional_for_wallet_risk(self):
        bot = make_bot(
            max_position_size_pct=5.0,
            risk_per_trade_pct=1.0,
            risk_model="percentage",
            risk_value=2.0,
            metadata={"trading_system": "futures_trading"},
        )
        decision = make_decision(
            risk_summary={"entry_price": 100.0, "stop_loss": 98.0}
        )
        result = _run(
            decision=decision,
            bot=bot,
            quantity=10.0,
            entry_price=100.0,
            portfolio_value_usd=1_000.0,
            market_snapshot=make_market_snapshot(close_price=100.0),
        )

        position = next(c for c in result.checks if c.name == "position_size_pct")
        risk = next(c for c in result.checks if c.name == "risk_per_trade")

        assert position.passed
        assert risk.passed
        assert not result.blocked


class TestStopLossRequired:
    def test_live_with_stop_loss_passes(self):
        decision = make_decision(
            mode="live",
            risk_summary={"entry_price": 50000.0, "quantity": 0.01, "stop_loss": 48000.0},
        )
        result = _run(decision=decision)
        check = next(c for c in result.checks if c.name == "stop_loss_required")
        assert check.passed

    def test_live_without_stop_loss_blocks(self, monkeypatch):
        import src.guards.risk_guard as mod
        monkeypatch.setattr(mod, "_DEFAULT_MAX_PRICE_SLIPPAGE_PCT", 1.0)

        # Override setting for this test
        from unittest.mock import patch
        with patch("src.guards.risk_guard.settings") as mock_settings:
            mock_settings.require_stop_loss_live = True
            mock_settings.max_slippage_pct = 1.0
            mock_settings.max_spread_pct = 2.0
            decision = make_decision(
                mode="live",
                risk_summary={"entry_price": 50000.0, "quantity": 0.01},  # no stop_loss
            )
            guard = RiskExecutionGuard()
            bot = make_bot()
            us = make_user_settings()
            snap = make_market_snapshot()
            result = guard.check(
                decision=decision,
                bot=bot,
                user_settings=us,
                open_trade_count=0,
                market_snapshot=snap,
                portfolio_value_usd=PORTFOLIO,
                daily_loss_usd=0.0,
                quantity=0.01,
                entry_price=50000.0,
            )
        check = next(c for c in result.checks if c.name == "stop_loss_required")
        assert not check.passed
        assert result.blocked

    def test_paper_without_stop_loss_blocks(self):
        decision = make_decision(
            mode="paper",
            risk_summary={"entry_price": 50000.0, "quantity": 0.01},  # no stop_loss
        )
        result = _run(decision=decision)
        check = next(c for c in result.checks if c.name == "stop_loss_required")
        assert not check.passed
        assert result.blocked


class TestPriceSlippage:
    def test_small_slippage_passes(self):
        # Entry 50000, current 50000 → 0% slippage
        snap = make_market_snapshot(close_price=50_000.0)
        result = _run(entry_price=50_000.0, market_snapshot=snap)
        check = next(c for c in result.checks if c.name == "price_slippage")
        assert check.passed

    def test_large_slippage_blocks(self):
        # Entry 50000, current 60000 → 20% slippage >> 1% limit
        snap = make_market_snapshot(close_price=60_000.0)
        result = _run(entry_price=50_000.0, market_snapshot=snap)
        check = next(c for c in result.checks if c.name == "price_slippage")
        assert not check.passed
        assert result.blocked

    def test_no_snapshot_blocks(self):
        result = _run(market_snapshot=None)
        check = next(c for c in result.checks if c.name == "price_slippage")
        assert not check.passed
        assert result.blocked


class TestSpreadLimit:
    def test_low_spread_passes(self):
        snap = make_market_snapshot(spread_pct=0.1)
        result = _run(market_snapshot=snap)
        check = next(c for c in result.checks if c.name == "spread_limit")
        assert check.passed

    def test_high_spread_blocks(self):
        snap = make_market_snapshot(spread_pct=5.0)  # > 2% default limit
        result = _run(market_snapshot=snap)
        check = next(c for c in result.checks if c.name == "spread_limit")
        assert not check.passed
        assert result.blocked

    def test_no_spread_data_passes_advisory(self):
        snap = make_market_snapshot(spread_pct=None)
        result = _run(market_snapshot=snap)
        check = next(c for c in result.checks if c.name == "spread_limit")
        assert check.passed   # advisory pass when spread not in snapshot


class TestAllPassed:
    def test_clean_decision_passes_all(self):
        result = _run()
        assert not result.blocked
        assert result.reason == "all checks passed"
        failed = [c for c in result.checks if not c.passed]
        assert not failed

    def test_result_to_dict(self):
        result = _run()
        d = result.to_dict()
        assert "blocked" in d
        assert "checks" in d
        assert isinstance(d["checks"], list)
