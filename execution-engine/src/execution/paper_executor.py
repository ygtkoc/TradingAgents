"""
PaperExecutor - paper trade persistence with no live exchange dependency.

NEVER makes real exchange API calls.
Paper mode writes a normal open trade row plus trade events using the latest
market snapshot / entry price and reserves paper balance when opening.
"""
from __future__ import annotations

from typing import Any
from uuid import uuid4

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
        risk = self._risk_fields(
            decision=decision,
            bot=bot,
            entry_price=resolved_entry_price,
            quantity=float(order.quantity),
            notional=notional,
        )
        reservation_id = uuid4().hex
        reserved = await self._paper_acct.reserve_for_open(
            user_id=decision.user_id,
            trade_id=None,
            notional=risk["reserve_amount"],
            symbol=order.symbol,
            reservation_id=reservation_id,
        )
        if not reserved:
            raise RuntimeError(
                f"Paper account has insufficient balance for {order.symbol} "
                f"(requested risk reserve {risk['reserve_amount']:.2f})"
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
            filled_quantity=order.quantity,
            avg_fill_price=resolved_entry_price,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            pnl=0.0,
            pnl_pct=0.0,
            risk_amount=risk["risk_amount"],
            risk_percent=risk["risk_percent"],
            risk_reward_ratio=risk["risk_reward_ratio"],
            expected_reward=risk["expected_reward"],
            notional=notional,
            metadata={
                "simulated": True,
                "paper_execution": True,
                "paper_fill_status": "filled",
                "market_snapshot_id": market_snapshot.id if market_snapshot else None,
                "bot_mode": bot.mode if bot else None,
                "reserved_on_open": True,
                "reserved_amount": risk["reserve_amount"],
                "notional": notional,
                "leverage": risk["leverage"],
                "margin_required": risk["margin_required"],
                "margin_percent": risk["margin_percent"],
                "sizing_model": risk["sizing_model"],
                "reservation_id": reservation_id,
                "reward_plan": risk["reward_plan"],
                "tp_plan": risk["tp_plan"],
            },
        )

        try:
            trade = await self._trade_repo.create(trade_insert)
            await self._paper_acct.attach_open_reservation(
                user_id=decision.user_id,
                trade_id=trade.id,
                reservation_id=reservation_id,
            )
        except Exception as exc:
            await self._paper_acct.release_open_reservation(
                user_id=decision.user_id,
                reservation_id=reservation_id,
                symbol=order.symbol,
                reason=str(exc),
            )
            raise

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
                    "notional": notional,
                    "risk_amount": risk["risk_amount"],
                    "risk_percent": risk["risk_percent"],
                    "reward_plan": risk["reward_plan"],
                    "tp_plan": risk["tp_plan"],
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

    @staticmethod
    def _get_float(source: dict, key: str) -> float | None:
        try:
            value = source.get(key)
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _risk_fields(
        self,
        *,
        decision: TradeDecision,
        bot: Bot | None,
        entry_price: float,
        quantity: float,
        notional: float,
    ) -> dict[str, Any]:
        risk_summary = decision.risk_summary or {}
        risk_amount = self._get_float(risk_summary, "risk_amount")
        stop_loss = self._get_float(risk_summary, "stop_loss")
        if risk_amount is None and stop_loss and stop_loss > 0:
            risk_amount = abs(entry_price - stop_loss) * quantity

        risk_percent = self._get_float(risk_summary, "risk_percent")
        if risk_percent is None and bot is not None:
            if bot.risk_model == "fixed_usd":
                risk_percent = None
            else:
                risk_percent = float(bot.risk_value or bot.risk_per_trade_pct or 0)

        risk_reward_ratio = (
            self._get_float(risk_summary, "risk_reward_ratio")
            or (float(bot.risk_reward_ratio) if bot is not None else None)
        )
        expected_reward = self._get_float(risk_summary, "expected_reward")
        if expected_reward is None and risk_amount is not None and risk_reward_ratio:
            expected_reward = risk_amount * risk_reward_ratio
        reward_plan = risk_summary.get("reward_plan") or {}
        tp_plan = risk_summary.get("tp_plan") or reward_plan.get("levels") or []

        reserve_amount = risk_amount if risk_amount is not None and risk_amount > 0 else notional
        reserve_amount = min(max(reserve_amount, 0.0), notional)

        leverage = self._get_float(risk_summary, "leverage") or 1.0
        margin_required = self._get_float(risk_summary, "margin_required")
        if margin_required is None and leverage > 0:
            margin_required = notional / leverage
        margin_percent = self._get_float(risk_summary, "margin_percent")
        sizing_model = risk_summary.get("sizing_model")

        return {
            "risk_amount": risk_amount,
            "risk_percent": risk_percent,
            "risk_reward_ratio": risk_reward_ratio,
            "expected_reward": expected_reward,
            "reward_plan": reward_plan,
            "tp_plan": tp_plan,
            "reserve_amount": reserve_amount,
            "leverage": leverage,
            "margin_required": margin_required,
            "margin_percent": margin_percent,
            "sizing_model": sizing_model,
        }
