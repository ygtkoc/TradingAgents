"""
OrderBuilder — constructs exchange OrderRequest from a TradeDecision.

Rules:
  - Derives side from final_decision (open_long → buy, open_short → sell)
  - Derives quantity from risk_summary.quantity, or computes it from
    portfolio value and position size if not present
  - Derives price from risk_summary.entry_price or market snapshot
  - Always includes a deterministic client_order_id for idempotency
  - Never mutates the decision or market snapshot objects

client_order_id format: sha256(decision_id + bot_id + symbol + side)[:32]
This ensures that if the same decision is retried, Binance sees the same
client order ID and rejects duplicates gracefully (-2010 DUPLICATE_ORDER).
"""
from __future__ import annotations

import hashlib
from typing import Optional

from src.db.models import MarketSnapshot, TradeDecision
from src.exchanges.base import OrderRequest
from src.logging_config import get_logger

log = get_logger(__name__)

_SIDE_MAP = {
    "open_long":  "buy",
    "open_short": "sell",
}


class OrderBuildError(Exception):
    """Raised when an order cannot be built from the given decision."""


class OrderBuilder:
    """
    Constructs an OrderRequest from a TradeDecision and market context.

    Args:
        portfolio_value_usd: Current portfolio value used for quantity sizing
                             when risk_summary.quantity is not explicitly set.
    """

    def __init__(self, portfolio_value_usd: float) -> None:
        self._portfolio_value = portfolio_value_usd

    def build(
        self,
        decision: TradeDecision,
        market_snapshot: Optional[MarketSnapshot],
    ) -> tuple[OrderRequest, float]:
        """
        Build an OrderRequest from the decision.

        Returns:
            (order_request, entry_price)

        Raises:
            OrderBuildError: If the order cannot be constructed safely.
        """
        side = _SIDE_MAP.get(decision.final_decision)
        if side is None:
            raise OrderBuildError(
                f"Cannot derive order side from final_decision '{decision.final_decision}'. "
                f"Supported: {list(_SIDE_MAP)}"
            )

        entry_price = self._derive_entry_price(decision, market_snapshot)
        quantity    = self._derive_quantity(decision, entry_price)

        if entry_price <= 0:
            raise OrderBuildError(f"Invalid entry_price: {entry_price}")
        if quantity <= 0:
            raise OrderBuildError(f"Invalid quantity: {quantity}")

        client_order_id = self._make_client_order_id(decision, side)
        stop_loss       = self._get_float(decision.risk_summary, "stop_loss")
        take_profit     = self._get_float(decision.risk_summary, "take_profit")
        order_type      = decision.risk_summary.get("order_type", "market")

        log.debug(
            "order_builder.built",
            decision_id=decision.id,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            order_type=order_type,
            has_stop_loss=stop_loss is not None,
            has_take_profit=take_profit is not None,
        )

        return (
            OrderRequest(
                exchange=decision.exchange,
                symbol=decision.symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=entry_price if order_type == "limit" else None,
                client_order_id=client_order_id,
                stop_loss=stop_loss,
                take_profit=take_profit,
                time_in_force=decision.risk_summary.get("time_in_force", "GTC"),
                metadata={
                    "decision_id": decision.id,
                    "bot_id": decision.bot_id,
                    "mode": decision.mode,
                },
            ),
            entry_price,
        )

    # ── Private helpers ────────────────────────────────────────────────────────

    def _derive_entry_price(
        self,
        decision: TradeDecision,
        market_snapshot: Optional[MarketSnapshot],
    ) -> float:
        """
        Entry price priority:
          1. risk_summary.entry_price (agent-specified)
          2. market_snapshot.close_price (current market price)
          3. Raise OrderBuildError
        """
        agent_price = self._get_float(decision.risk_summary, "entry_price")
        if agent_price and agent_price > 0:
            return agent_price

        if market_snapshot and market_snapshot.close_price > 0:
            return market_snapshot.close_price

        raise OrderBuildError(
            "Cannot determine entry price: no risk_summary.entry_price and no market snapshot"
        )

    def _derive_quantity(self, decision: TradeDecision, entry_price: float) -> float:
        """
        Quantity priority:
          1. risk_summary.quantity (agent-specified)
          2. risk_summary.position_size_pct applied to portfolio_value_usd
          3. fallback: 1% of portfolio at current price (minimal safe default)
        """
        explicit_qty = self._get_float(decision.risk_summary, "quantity")
        if explicit_qty and explicit_qty > 0:
            return explicit_qty

        size_pct = self._get_float(decision.risk_summary, "position_size_pct")
        if size_pct and size_pct > 0 and entry_price > 0:
            position_usd = self._portfolio_value * (size_pct / 100.0)
            return round(position_usd / entry_price, 8)

        # Fallback: 1% of portfolio
        if self._portfolio_value > 0 and entry_price > 0:
            log.warning(
                "order_builder.using_fallback_quantity",
                decision_id=decision.id,
                portfolio=self._portfolio_value,
            )
            return round(self._portfolio_value * 0.01 / entry_price, 8)

        raise OrderBuildError("Cannot compute quantity: no explicit quantity and no portfolio value")

    def _make_client_order_id(self, decision: TradeDecision, side: str) -> str:
        """
        Deterministic idempotency key for the exchange.
        Same decision + side always produces the same client_order_id.
        Binance limit: 36 chars; we use 32.
        """
        raw = f"{decision.id}:{decision.bot_id}:{decision.symbol}:{side}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    @staticmethod
    def _get_float(d: dict, key: str) -> Optional[float]:
        val = d.get(key)
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None
