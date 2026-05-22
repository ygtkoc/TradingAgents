"""
Tests for PaperExecutor and ShadowExecutor.

Verifies:
  - No real exchange API calls are made
  - Trade rows created with correct mode
  - Events written
  - OrderBuilder produces correct side mapping
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db.models import TradeStatus
from src.execution.order_builder import OrderBuildError, OrderBuilder
from src.execution.paper_executor import PaperExecutor
from src.execution.shadow_executor import ShadowExecutor
from src.exchanges.base import OrderRequest, OrderResult
from tests.conftest import (
    make_bot,
    make_decision,
    make_market_snapshot,
    make_trade,
)


# ── OrderBuilder ──────────────────────────────────────────────────────────────

class TestOrderBuilder:
    def test_open_long_maps_to_buy(self):
        decision = make_decision(final_decision="open_long")
        snap = make_market_snapshot(close_price=50_000.0)
        builder = OrderBuilder(portfolio_value_usd=10_000.0)
        order, price = builder.build(decision, snap)
        assert order.side == "buy"

    def test_open_short_maps_to_sell(self):
        decision = make_decision(
            final_decision="open_short",
            risk_summary={"entry_price": 50000.0, "quantity": 0.01, "stop_loss": 52000.0},
        )
        snap = make_market_snapshot(close_price=50_000.0)
        builder = OrderBuilder(portfolio_value_usd=10_000.0)
        order, price = builder.build(decision, snap)
        assert order.side == "sell"

    def test_unsupported_decision_raises(self):
        decision = make_decision(final_decision="wait")
        snap = make_market_snapshot()
        builder = OrderBuilder(portfolio_value_usd=10_000.0)
        with pytest.raises(OrderBuildError):
            builder.build(decision, snap)

    def test_quantity_from_risk_summary(self):
        decision = make_decision(
            risk_summary={"entry_price": 50000.0, "quantity": 0.05, "stop_loss": 48000.0}
        )
        snap = make_market_snapshot(close_price=50_000.0)
        builder = OrderBuilder(portfolio_value_usd=10_000.0)
        order, _ = builder.build(decision, snap)
        assert order.quantity == pytest.approx(0.05)

    def test_quantity_fallback_from_portfolio(self):
        # No explicit quantity → uses position_size_pct
        decision = make_decision(
            risk_summary={
                "entry_price": 50000.0,
                "position_size_pct": 10.0,
                "stop_loss": 48000.0,
            }
        )
        snap = make_market_snapshot(close_price=50_000.0)
        builder = OrderBuilder(portfolio_value_usd=10_000.0)
        order, _ = builder.build(decision, snap)
        # 10% of $10,000 = $1,000 / $50,000 = 0.02 BTC
        assert order.quantity == pytest.approx(0.02, rel=1e-3)

    def test_entry_price_from_risk_summary(self):
        decision = make_decision(
            risk_summary={"entry_price": 48000.0, "quantity": 0.01}
        )
        snap = make_market_snapshot(close_price=50_000.0)
        builder = OrderBuilder(portfolio_value_usd=10_000.0)
        _, price = builder.build(decision, snap)
        assert price == pytest.approx(48000.0)

    def test_entry_price_fallback_to_market(self):
        decision = make_decision(
            risk_summary={"quantity": 0.01}  # no entry_price
        )
        snap = make_market_snapshot(close_price=52_000.0)
        builder = OrderBuilder(portfolio_value_usd=10_000.0)
        _, price = builder.build(decision, snap)
        assert price == pytest.approx(52_000.0)

    def test_client_order_id_is_deterministic(self):
        decision = make_decision()
        snap = make_market_snapshot()
        builder = OrderBuilder(portfolio_value_usd=10_000.0)
        order1, _ = builder.build(decision, snap)
        order2, _ = builder.build(decision, snap)
        assert order1.client_order_id == order2.client_order_id

    def test_client_order_id_is_32_chars(self):
        decision = make_decision()
        snap = make_market_snapshot()
        builder = OrderBuilder(portfolio_value_usd=10_000.0)
        order, _ = builder.build(decision, snap)
        assert len(order.client_order_id) == 32

    def test_stop_loss_included_in_order(self):
        decision = make_decision(
            risk_summary={"entry_price": 50000.0, "quantity": 0.01, "stop_loss": 47000.0}
        )
        snap = make_market_snapshot()
        builder = OrderBuilder(portfolio_value_usd=10_000.0)
        order, _ = builder.build(decision, snap)
        assert order.stop_loss == pytest.approx(47000.0)

    def test_no_snapshot_and_no_risk_price_raises(self):
        decision = make_decision(risk_summary={"quantity": 0.01})  # no entry_price
        builder = OrderBuilder(portfolio_value_usd=10_000.0)
        with pytest.raises(OrderBuildError):
            builder.build(decision, None)


# ── PaperExecutor ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_paper_executor_creates_paper_trade():
    decision = make_decision(mode="paper")
    bot = make_bot()
    snap = make_market_snapshot(close_price=50_000.0)

    order = OrderRequest(
        exchange="binance",
        symbol="BTC/USDT",
        side="buy",
        order_type="market",
        quantity=0.01,
        client_order_id="test-client-id",
    )

    expected_trade = make_trade(mode="paper", status=TradeStatus.SIMULATED.value)

    executor = PaperExecutor()

    with (
        patch.object(executor._trade_repo, "create", AsyncMock(return_value=expected_trade)),
        patch.object(executor._event_repo, "create", AsyncMock()),
        patch.object(executor._paper_acct, "reserve_for_open", AsyncMock(return_value=True)),
        patch.object(executor._paper_acct, "attach_open_reservation", AsyncMock()),
    ):
        trade = await executor.execute(
            decision=decision,
            bot=bot,
            order=order,
            entry_price=50_000.0,
            market_snapshot=snap,
        )

    assert trade.mode == "paper"
    assert trade.status == TradeStatus.SIMULATED.value


@pytest.mark.asyncio
async def test_paper_executor_reserves_risk_not_notional():
    decision = make_decision(
        mode="paper",
        risk_summary={
            "entry_price": 100.0,
            "quantity": 10.0,
            "stop_loss": 98.0,
            "take_profit": 104.0,
            "risk_amount": 20.0,
            "risk_percent": 2.0,
            "risk_reward_ratio": 2.0,
        },
    )
    bot = make_bot()
    snap = make_market_snapshot(close_price=100.0)
    order = OrderRequest(
        exchange="binance",
        symbol="TEST/USDT",
        side="buy",
        order_type="market",
        quantity=10.0,
        stop_loss=98.0,
        take_profit=104.0,
        client_order_id="test-client-id",
    )

    executor = PaperExecutor()
    inserted_rows = []
    reserve_mock = AsyncMock(return_value=True)

    async def _capture(row):
        inserted_rows.append(row)
        return make_trade(mode="paper", status="open", entry_price=100.0, quantity=10.0)

    with (
        patch.object(executor._trade_repo, "create", side_effect=_capture),
        patch.object(executor._event_repo, "create", AsyncMock()),
        patch.object(executor._paper_acct, "reserve_for_open", reserve_mock),
        patch.object(executor._paper_acct, "attach_open_reservation", AsyncMock()),
    ):
        await executor.execute(
            decision=decision,
            bot=bot,
            order=order,
            entry_price=100.0,
            market_snapshot=snap,
        )

    assert reserve_mock.await_args.kwargs["notional"] == pytest.approx(20.0)
    assert inserted_rows[0].filled_quantity == pytest.approx(10.0)
    assert inserted_rows[0].avg_fill_price == pytest.approx(100.0)
    assert inserted_rows[0].risk_amount == pytest.approx(20.0)
    assert inserted_rows[0].notional == pytest.approx(1000.0)


@pytest.mark.asyncio
async def test_paper_executor_never_calls_real_exchange():
    """MockExchangeAdapter should be used — verify no real httpx calls."""
    import httpx
    decision = make_decision(mode="paper")
    bot = make_bot()
    snap = make_market_snapshot(close_price=50_000.0)

    order = OrderRequest(
        exchange="binance",
        symbol="BTC/USDT",
        side="buy",
        order_type="market",
        quantity=0.01,
        client_order_id="test-client-id",
    )

    executor = PaperExecutor()
    expected_trade = make_trade(mode="paper")

    real_calls = []
    real_send = httpx.AsyncClient.send

    async def _intercept(self, request, **kw):
        real_calls.append(request.url)
        return await real_send(self, request, **kw)

    with (
        patch.object(executor._trade_repo, "create", AsyncMock(return_value=expected_trade)),
        patch.object(executor._event_repo, "create", AsyncMock()),
        patch.object(executor._paper_acct, "reserve_for_open", AsyncMock(return_value=True)),
        patch.object(executor._paper_acct, "attach_open_reservation", AsyncMock()),
        patch("httpx.AsyncClient.send", new=_intercept),
    ):
        await executor.execute(
            decision=decision,
            bot=bot,
            order=order,
            entry_price=50_000.0,
            market_snapshot=snap,
        )

    assert not real_calls, f"Unexpected real HTTP calls: {real_calls}"


@pytest.mark.asyncio
async def test_paper_executor_writes_trade_event():
    decision = make_decision(mode="paper")
    bot = make_bot()
    snap = make_market_snapshot()
    order = OrderRequest(
        exchange="binance", symbol="BTC/USDT", side="buy",
        order_type="market", quantity=0.01,
    )

    executor = PaperExecutor()
    expected_trade = make_trade(mode="paper")

    event_mock = AsyncMock()
    with (
        patch.object(executor._trade_repo, "create", AsyncMock(return_value=expected_trade)),
        patch.object(executor._event_repo, "create", event_mock),
        patch.object(executor._paper_acct, "reserve_for_open", AsyncMock(return_value=True)),
        patch.object(executor._paper_acct, "attach_open_reservation", AsyncMock()),
    ):
        await executor.execute(
            decision=decision, bot=bot, order=order,
            entry_price=50_000.0, market_snapshot=snap,
        )

    event_mock.assert_called_once()
    call_args = event_mock.call_args[0][0]
    assert call_args.event_type == "paper_trade_opened"


# ── ShadowExecutor ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_shadow_executor_creates_shadow_trade():
    decision = make_decision(mode="shadow")
    bot = make_bot()
    snap = make_market_snapshot()
    order = OrderRequest(
        exchange="binance", symbol="BTC/USDT", side="buy",
        order_type="market", quantity=0.01,
    )

    executor = ShadowExecutor()
    expected_trade = make_trade(mode="shadow")

    with (
        patch.object(executor._trade_repo, "create", AsyncMock(return_value=expected_trade)),
        patch.object(executor._event_repo, "create", AsyncMock()),
    ):
        trade = await executor.execute(
            decision=decision, bot=bot, order=order,
            entry_price=50_000.0, market_snapshot=snap,
        )

    assert trade.mode == "shadow"


@pytest.mark.asyncio
async def test_shadow_executor_no_exchange_order_id():
    """Shadow trades have no exchange_order_id (no real order placed)."""
    decision = make_decision(mode="shadow")
    bot = make_bot()
    snap = make_market_snapshot()
    order = OrderRequest(
        exchange="binance", symbol="BTC/USDT", side="buy",
        order_type="market", quantity=0.01,
    )

    executor = ShadowExecutor()

    inserted_rows = []

    async def _capture(row):
        inserted_rows.append(row)
        return make_trade(mode="shadow")

    with (
        patch.object(executor._trade_repo, "create", side_effect=_capture),
        patch.object(executor._event_repo, "create", AsyncMock()),
    ):
        await executor.execute(
            decision=decision, bot=bot, order=order,
            entry_price=50_000.0, market_snapshot=snap,
        )

    assert len(inserted_rows) == 1
    assert inserted_rows[0].exchange_order_id is None
