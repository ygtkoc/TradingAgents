"""
Mock exchange adapter for paper and shadow execution.

NEVER makes real API calls.
Returns deterministic simulated order results.
Used for:
  - paper mode (no real order, create simulated trade)
  - shadow mode (record intended order, no real execution)
  - unit and integration tests
"""
from __future__ import annotations

import uuid
from typing import Optional

from src.exchanges.base import (
    BalanceResult,
    ExchangeAdapter,
    OrderRequest,
    OrderResult,
    PermissionCheckResult,
)
from src.logging_config import get_logger

log = get_logger(__name__)


class MockExchangeAdapter(ExchangeAdapter):
    """
    Simulated exchange adapter.

    Always returns success results with configurable price.
    All methods log their invocation so tests can verify no real calls were made.
    """

    def __init__(
        self,
        simulated_price: float = 50_000.0,
        simulated_balance_usd: float = 10_000.0,
    ) -> None:
        self._price = simulated_price
        self._balance = simulated_balance_usd

    async def check_permissions(self) -> PermissionCheckResult:
        """Mock: always returns safe permissions."""
        log.debug("mock_exchange.check_permissions")
        return PermissionCheckResult(
            can_trade=True,
            can_withdraw=False,    # Safe: no withdrawal permission
            has_read_permission=True,
            raw_permissions={"mock": True},
        )

    async def get_latest_price(self, symbol: str) -> float:
        log.debug("mock_exchange.get_latest_price", symbol=symbol)
        return self._price

    async def get_balance(self) -> BalanceResult:
        log.debug("mock_exchange.get_balance")
        return BalanceResult(
            free={"USDT": self._balance, "BTC": 0.1},
            total={"USDT": self._balance, "BTC": 0.1},
            quote_free=self._balance,
        )

    async def place_order(self, order: OrderRequest) -> OrderResult:
        """
        Simulate an order fill.

        NEVER makes a real API call. Returns a deterministic result.
        """
        log.debug(
            "mock_exchange.place_order",
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            order_type=order.order_type,
        )
        mock_order_id = f"mock-{uuid.uuid4().hex[:12]}"
        fill_price = order.price or self._price

        return OrderResult(
            order_id=mock_order_id,
            client_order_id=order.client_order_id,
            status="filled",
            filled_quantity=order.quantity,
            avg_fill_price=fill_price,
            raw_response={
                "mock": True,
                "orderId": mock_order_id,
                "status": "FILLED",
                "side": order.side.upper(),
                "symbol": order.symbol,
                "quantity": order.quantity,
                "price": fill_price,
            },
            success=True,
        )

    async def fetch_order(self, order_id: str, symbol: str) -> OrderResult:
        log.debug("mock_exchange.fetch_order", order_id=order_id)
        return OrderResult(
            order_id=order_id,
            client_order_id=None,
            status="filled",
            filled_quantity=0.0,
            avg_fill_price=self._price,
            raw_response={"mock": True, "orderId": order_id, "status": "FILLED"},
            success=True,
        )

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        log.debug("mock_exchange.cancel_order", order_id=order_id)
        return True
