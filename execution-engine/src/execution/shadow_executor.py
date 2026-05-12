"""
ShadowExecutor — records the intended trade for shadow/observation mode.

Shadow mode:
  - Reads all context and runs all guards (same as live)
  - Does NOT place any exchange order
  - Creates a trade row with mode='shadow' and status='simulated'
  - Useful for verifying bot logic against live market data before enabling live mode

NEVER makes real exchange API calls.
"""
from __future__ import annotations

from src.db.models import (
    Bot,
    MarketSnapshot,
    Trade,
    TradeDecision,
    TradeEventInsert,
    TradeInsert,
    TradeStatus,
)
from src.db.repositories import TradeEventRepository, TradeRepository
from src.exchanges.base import OrderRequest
from src.logging_config import get_logger

log = get_logger(__name__)


class ShadowExecutor:
    """
    Records what a live trade would have done, without placing a real order.
    """

    def __init__(self) -> None:
        self._trade_repo  = TradeRepository()
        self._event_repo  = TradeEventRepository()

    async def execute(
        self,
        *,
        decision: TradeDecision,
        bot: Bot,
        order: OrderRequest,
        entry_price: float,
        market_snapshot: MarketSnapshot | None,
    ) -> Trade:
        """
        Record the shadow trade (no exchange call).

        Returns:
            Trade row with mode='shadow' and status='simulated'.
        """
        log.info(
            "shadow_executor.recording_intended_order",
            decision_id=decision.id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            entry_price=entry_price,
        )

        trade_insert = TradeInsert(
            user_id=decision.user_id,
            bot_id=decision.bot_id,
            trade_decision_id=decision.id,
            agent_run_id=decision.agent_run_id,
            exchange=decision.exchange,
            symbol=decision.symbol,
            side=order.side,
            direction=decision.direction,
            mode="shadow",
            status=TradeStatus.SIMULATED.value,
            entry_price=entry_price,
            quantity=order.quantity,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            exchange_order_id=None,   # no real order placed
            filled_quantity=order.quantity,
            avg_fill_price=entry_price,
            metadata={
                "shadow": True,
                "intended_side": order.side,
                "intended_order_type": order.order_type,
                "client_order_id": order.client_order_id,
                "market_snapshot_id": market_snapshot.id if market_snapshot else None,
            },
        )

        trade = await self._trade_repo.create(trade_insert)

        await self._event_repo.create(TradeEventInsert(
            trade_id=trade.id,
            trade_decision_id=decision.id,
            bot_id=decision.bot_id,
            user_id=decision.user_id,
            event_type="shadow_order_recorded",
            details={
                "intended_side": order.side,
                "entry_price": entry_price,
                "quantity": order.quantity,
                "symbol": order.symbol,
                "note": "Shadow mode — no real order placed",
            },
        ))

        log.info(
            "shadow_executor.done",
            trade_id=trade.id,
            decision_id=decision.id,
        )
        return trade
