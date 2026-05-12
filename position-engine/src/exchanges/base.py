"""Exchange adapter interface for the Position Engine."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class OrderRequest:
    exchange:        str
    symbol:          str
    side:            str           # 'buy' | 'sell'
    order_type:      str           # 'market' | 'limit'
    quantity:        float
    price:           Optional[float] = None
    client_order_id: Optional[str]  = None
    time_in_force:   str            = "GTC"
    metadata:        dict[str, Any] = field(default_factory=dict)


@dataclass
class OrderResult:
    order_id:        str
    client_order_id: Optional[str]
    status:          str           # 'open' | 'filled' | 'partially_filled' | 'cancelled' | 'failed'
    filled_quantity: float
    avg_fill_price:  Optional[float]
    raw_response:    dict[str, Any]
    success:         bool
    error:           Optional[str]  = None


@dataclass
class PermissionCheckResult:
    can_trade:           bool
    can_withdraw:        bool
    has_read_permission: bool
    raw_permissions:     dict[str, Any]

    @property
    def safe(self) -> bool:
        return self.can_trade and not self.can_withdraw


@dataclass
class BalanceResult:
    free:       dict[str, float]
    total:      dict[str, float]
    quote_free: float = 0.0


class ExchangeAdapter(ABC):
    """Abstract exchange adapter used by both Execution and Position engines."""

    @abstractmethod
    async def check_permissions(self) -> PermissionCheckResult: ...

    @abstractmethod
    async def get_latest_price(self, symbol: str) -> float: ...

    @abstractmethod
    async def get_balance(self) -> BalanceResult: ...

    @abstractmethod
    async def place_order(self, order: OrderRequest) -> OrderResult: ...

    @abstractmethod
    async def fetch_order(self, order_id: str, symbol: str) -> OrderResult: ...

    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> bool: ...

    async def close(self) -> None:
        """Release resources (e.g., HTTP client). Override as needed."""
