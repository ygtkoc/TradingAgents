"""
PaperExecutor - paper trade persistence with no live exchange dependency.

NEVER makes real exchange API calls.
Paper mode writes a normal open trade row plus trade events using the latest
market snapshot / entry price and reserves paper balance when opening.
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
from src.services.paper_account import PaperAccountService

log = get_logger(__name__)


class PaperExecutor:
    """
    Executes a trade decision in paper mode with no exchange dependency.

    Returns a Trade row created in the database.
    """

    def __init__(self) -> None:
        self._trade_repo = TradeRepository()
        self._event_repo = TradeEventRepository()
        self._paper_acct = PaperAccountService()

    async def execute(
        self,
        *,
        decision: TradeDecision,
        bot: Bot | None,
        order: OrderRequest,
        entry_price: float,
        market_snapshot: MarketSnapshot | None,
    ) -> Trade:
        """
        Persist a paper-mode open trade and reserve paper balance.

        Returns:
            Trade row with mode='paper' and status='open'.
        """
        resolved_entry_price = float(
            entry_price or (market_snapshot.close_price if market_snapshot else 0.0)
        )
        if resolved_entry_price <= 0:
            raise RuntimeError("Paper execution requires a valid entry price")

        notional = resolved_entry_price * float(order.quantity)
        reserved = await self._paper_acct.reserve_for_open(
            user_id=decision.user_id,
            trade_id=None,
            notional=notional,
            symbol=order.symbol,
        )
        if not reserved:
            raise RuntimeError(
                f"Paper account has insufficient balance for {order.symbol} "
                f"(requested notional {notional:.2f})"
            )

        log.info(
            "paper_execution.start",
            decision_id=decision.id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            entry_price=resolved_entry_price,
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
            mode="paper",
            status=TradeStatus.OPEN.value,
            lifecycle_status="idle",
            entry_price=resolved_entry_price,
            quantity=order.quantity,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            exchange_order_id=None,
            filled_quantity=None,
            avg_fill_price=None,
            metadata={
                "simulated": True,
                "paper_execution": True,
                "market_snapshot_id": market_snapshot.id if market_snapshot else None,
                "bot_mode": bot.mode if bot else None,
            },
        )

        trade = await self._trade_repo.create(trade_insert)

        log.info(
            "paper_trade.created",
            trade_id=trade.id,
            decision_id=decision.id,
            symbol=decision.symbol,
            side=order.side,
            quantity=order.quantity,
            entry_price=resolved_entry_price,
        )

        await self._event_repo.create(
            TradeEventInsert(
                trade_id=trade.id,
                trade_decision_id=decision.id,
                bot_id=decision.bot_id,
                user_id=decision.user_id,
                event_type="paper_trade_opened",
                details={
                    "fill_price": resolved_entry_price,
                    "filled_qty": order.quantity,
                    "side": order.side,
                    "symbol": order.symbol,
                    "mode": "paper",
                    "status": TradeStatus.OPEN.value,
                },
            )
        )

        log.info(
            "paper_execution.completed",
            trade_id=trade.id,
            decision_id=decision.id,
            fill_price=resolved_entry_price,
            filled_qty=order.quantity,
        )
        return trade
