"""
Mock exchange adapter for paper and shadow mode lifecycle operations.

NEVER makes real API calls.
Supports simulated price injection for test scenarios.
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
    Simulated exchange adapter for paper/shadow mode and tests.

    Price can be set externally to simulate market movements.
    """

    def __init__(
        self,
        simulated_price: float = 50_000.0,
        simulated_balance_usd: float = 10_000.0,
        simulated_order_status: str = "filled",  # used by fetch_order in tests
    ) -> None:
        self._price   = simulated_price
        self._balance = simulated_balance_usd
        self._order_status = simulated_order_status
        self._orders: dict[str, OrderResult] = {}

    def set_price(self, price: float) -> None:
        """Inject a new price for test scenarios."""
        self._price = price

    def set_order_status(self, status: str) -> None:
        """Override the status returned by fetch_order."""
        self._order_status = status

    async def check_permissions(self) -> PermissionCheckResult:
        log.debug("mock_exchange.check_permissions")
        return PermissionCheckResult(
            can_trade=True,
            can_withdraw=False,
            has_read_permission=True,
            raw_permissions={"mock": True},
        )

    async def get_latest_price(self, symbol: str) -> float:
        log.debug("mock_exchange.get_latest_price", symbol=symbol)
        return self._price

    async def get_balance(self) -> BalanceResult:
        log.debug("mock_exchange.get_balance")
        return BalanceResult(
            free={"USDT": self._balance, "BTC": 1.0},
            total={"USDT": self._balance, "BTC": 1.0},
            quote_free=self._balance,
        )

    async def place_order(self, order: OrderRequest) -> OrderResult:
        log.debug(
            "mock_exchange.place_order",
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
        )
        mock_id = f"mock-{uuid.uuid4().hex[:12]}"
        result = OrderResult(
            order_id=mock_id,
            client_order_id=order.client_order_id,
            status=self._order_status,
            filled_quantity=order.quantity if self._order_status == "filled" else 0.0,
            avg_fill_price=self._price,
            raw_response={"mock": True, "orderId": mock_id, "status": self._order_status.upper()},
            success=self._order_status not in ("rejected", "cancelled", "failed"),
        )
        self._orders[mock_id] = result
        return result

    async def fetch_order(self, order_id: str, symbol: str) -> OrderResult:
        log.debug("mock_exchange.fetch_order", order_id=order_id)
        # Return the stored order if it exists, else build one from current state
        if order_id in self._orders:
            stored = self._orders[order_id]
            # Return with current mock status (allows status injection)
            return OrderResult(
                order_id=order_id,
                client_order_id=stored.client_order_id,
                status=self._order_status,
                filled_quantity=stored.filled_quantity,
                avg_fill_price=stored.avg_fill_price,
                raw_response=stored.raw_response,
                success=self._order_status not in ("rejected", "cancelled", "failed"),
            )
        return OrderResult(
            order_id=order_id,
            client_order_id=None,
            status=self._order_status,
            filled_quantity=0.0,
            avg_fill_price=self._price,
            raw_response={"mock": True, "orderId": order_id, "status": self._order_status.upper()},
            success=self._order_status not in ("rejected", "cancelled", "failed"),
        )

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        log.debug("mock_exchange.cancel_order", order_id=order_id)
        return True
