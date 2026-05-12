"""
Exchange adapter interface.

All exchange adapters implement this interface.
The Execution Engine calls adapters only during live execution,
and only after all security and risk checks pass.

SECURITY:
  Adapters receive API credentials only at construction time.
  They must never log or store credentials beyond the call scope.
  The caller (LiveExecutor) zeroes credentials after the adapter is discarded.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class OrderRequest:
    """Parameters for placing an order on an exchange."""
    exchange:         str
    symbol:           str
    side:             str           # 'buy' | 'sell'
    order_type:       str           # 'market' | 'limit'
    quantity:         float
    price:            Optional[float] = None
    client_order_id:  Optional[str] = None   # idempotency key for exchange
    stop_loss:        Optional[float] = None
    take_profit:      Optional[float] = None
    time_in_force:    str = "GTC"
    metadata:         dict[str, Any] = field(default_factory=dict)


@dataclass
class OrderResult:
    """Result of placing or fetching an order."""
    order_id:         str
    client_order_id:  Optional[str]
    status:           str           # 'open' | 'filled' | 'cancelled' | 'failed'
    filled_quantity:  float
    avg_fill_price:   Optional[float]
    raw_response:     dict[str, Any]
    success:          bool
    error:            Optional[str] = None
    exchange_ts:      Optional[str] = None


@dataclass
class PermissionCheckResult:
    """Result of verifying exchange API key permissions."""
    can_trade:          bool
    can_withdraw:       bool
    has_read_permission: bool
    raw_permissions:    dict[str, Any]

    @property
    def safe(self) -> bool:
        """
        True if the key is safe to use for trading:
        can_trade=True AND can_withdraw=False.

        Withdrawal permission on a trading key is a critical security violation.
        """
        return self.can_trade and not self.can_withdraw


@dataclass
class BalanceResult:
    """Account balance summary."""
    free:  dict[str, float]   # currency → available balance
    total: dict[str, float]   # currency → total balance
    quote_free: float = 0.0   # convenience: free balance in quote currency


class ExchangeAdapter(ABC):
    """
    Abstract exchange adapter.

    Concrete implementations:
      - MockExchangeAdapter  (paper/shadow/testing — no real API calls)
      - BinanceExchangeAdapter  (live — real Binance API)

    All methods must be async and must never log API keys or secrets.
    """

    @abstractmethod
    async def check_permissions(self) -> PermissionCheckResult:
        """
        Verify that the API key has exactly the right permissions:
        can_trade=True, can_withdraw=False.

        Must be called before every live order placement.
        If can_withdraw=True, raise an exception and block the trade.
        """
        ...

    @abstractmethod
    async def get_latest_price(self, symbol: str) -> float:
        """Get the current mid-price for a symbol."""
        ...

    @abstractmethod
    async def get_balance(self) -> BalanceResult:
        """Fetch current account balance."""
        ...

    @abstractmethod
    async def place_order(self, order: OrderRequest) -> OrderResult:
        """
        Place an order and return the result.

        For market orders, fills immediately; for limit orders, may be open.
        Must include client_order_id if provided (for idempotency).
        """
        ...

    @abstractmethod
    async def fetch_order(self, order_id: str, symbol: str) -> OrderResult:
        """
        Fetch the current status of an existing order.

        Used for:
        - Confirming fill after placement
        - Recovery after DB write failure
        """
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """
        Cancel an open order.

        Returns True if cancelled, False if already filled or not found.
        Used in error recovery paths only.
        """
        ...
