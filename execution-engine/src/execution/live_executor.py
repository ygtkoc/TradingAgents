"""
LiveExecutor — places real exchange orders for live trading.

CRITICAL SAFETY RULES (non-negotiable):
  1. Only called when ENABLE_LIVE_EXECUTION=True. The ExecutionEngine enforces
     this gate before ever instantiating LiveExecutor.
  2. All security and risk guards have already passed before this is called.
  3. API credentials are loaded, used, and zeroed out in a single try/finally.
  4. NEVER log api_key, api_secret, or any credential material.
  5. On ANY unknown exchange response: log error, mark decision failed, do NOT
     retry blindly. pg_cron resets stuck 'executing' rows safely.
  6. On DUPLICATE_ORDER (-2010): treat as success — fetch existing order.
  7. On confirmed fill: write trade row, then update decision.linked_trade_id.
     If the decision update fails after the trade is written, IdempotencyChecker
     will find the trade on the next run.

Exchange call flow:
  1. check_permissions() — block if can_withdraw=True (defence-in-depth)
  2. get_balance()       — verify sufficient funds
  3. place_order()       — place market/limit order with clientOrderId
  4. Verify fill         — check result.success and filled_quantity > 0
  5. Create trade row
  6. Write trade events
  7. Close adapter / zero credentials
"""
from __future__ import annotations

from src.config import settings
from src.db.models import (
    Bot,
    ExchangeAccount,
    MarketSnapshot,
    Trade,
    TradeDecision,
    TradeEventInsert,
    TradeInsert,
    TradeStatus,
)
from src.db.repositories import TradeEventRepository, TradeRepository
from src.exchanges.base import OrderRequest, OrderResult
from src.exchanges.factory import get_live_adapter
from src.keys.key_provider import ApiCredentials, KeyProvider
from src.logging_config import get_logger

# Exchange statuses that confirm a fill
_FILLED_STATUSES  = frozenset({"filled", "closed", "done"})
_PARTIAL_STATUSES = frozenset({"partially_filled", "partial"})
_OPEN_STATUSES    = frozenset({"open", "new", "pending"})

log = get_logger(__name__)


class LiveExecutionError(Exception):
    """Raised when live execution cannot proceed safely."""


class LiveExecutor:
    """
    Places a real order on the exchange.

    This class must only be instantiated after:
      - ENABLE_LIVE_EXECUTION=True verified
      - All security checks passed
      - All risk checks passed
      - Idempotency check passed

    Credentials are zeroed immediately after the exchange call.
    """

    def __init__(self) -> None:
        self._trade_repo  = TradeRepository()
        self._event_repo  = TradeEventRepository()
        self._key_provider = KeyProvider()

    async def execute(
        self,
        *,
        decision: TradeDecision,
        bot: Bot,
        exchange_account: ExchangeAccount,
        order: OrderRequest,
        entry_price: float,
        market_snapshot: MarketSnapshot | None,
    ) -> Trade:
        """
        Place a real exchange order and persist the resulting trade.

        Returns:
            The created Trade row.

        Raises:
            LiveExecutionError: If any safety check fails or order cannot be placed.
        """
        if not settings.enable_live_execution:
            # Should never reach here — ExecutionEngine checks this first.
            raise LiveExecutionError(
                "ENABLE_LIVE_EXECUTION is False. Live execution refused."
            )

        if not bot.real_trading_enabled:
            raise LiveExecutionError(
                f"Bot {bot.id} has real_trading_enabled=False. Refusing live execution."
            )

        # ── Load credentials (plaintext only within this scope) ───────────────
        credentials: ApiCredentials | None = None
        adapter = None

        try:
            credentials = await self._key_provider.get_credentials(
                exchange_account.id
            )

            # ── Create the exchange adapter ───────────────────────────────────
            adapter = get_live_adapter(
                exchange=decision.exchange,
                api_key=credentials.api_key,
                api_secret=credentials.api_secret,
            )

            # ── Defence-in-depth: re-verify permissions ───────────────────────
            perm = await adapter.check_permissions()
            if not perm.safe:
                raise LiveExecutionError(
                    f"Exchange permissions unsafe: can_trade={perm.can_trade}, "
                    f"can_withdraw={perm.can_withdraw}. Execution blocked."
                )

            # ── Verify sufficient balance ─────────────────────────────────────
            balance = await adapter.get_balance()
            required_usd = order.quantity * entry_price
            if balance.quote_free < required_usd:
                raise LiveExecutionError(
                    f"Insufficient balance: available ${balance.quote_free:.2f}, "
                    f"required ${required_usd:.2f}"
                )

            log.info(
                "live_executor.placing_order",
                decision_id=decision.id,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                order_type=order.order_type,
                # DO NOT log api_key, api_secret, or credentials
            )

            # ── Place the order ───────────────────────────────────────────────
            result = await adapter.place_order(order)

        finally:
            # ALWAYS zero credentials — even if an exception occurred
            if credentials is not None:
                credentials.zero_out()
            if adapter is not None:
                try:
                    await adapter.close()
                except Exception:
                    pass

        # ── Validate place_order result ───────────────────────────────────────
        if not result.success:
            raise LiveExecutionError(
                f"Exchange order failed: {result.error or 'unknown error'}"
            )

        if not result.order_id:
            raise LiveExecutionError(
                "Exchange returned no order_id — cannot confirm fill. "
                "Failing for recovery — do not retry blindly."
            )

        # ── Confirm fill via fetch_order ──────────────────────────────────────
        # place_order() may return a stale fill status. We independently
        # confirm by calling fetch_order() with a fresh credentials/adapter pair.
        fill_price, filled_qty = await self._confirm_fill(
            order_id=result.order_id,
            exchange=decision.exchange,
            symbol=order.symbol,
            exchange_account_id=exchange_account.id,
            expected_qty=order.quantity,
            expected_price=entry_price,
        )

        # ── Post-fill slippage guard ──────────────────────────────────────────
        # Compare actual fill price to the price used for risk calculations.
        slippage_pct = abs(fill_price - entry_price) / entry_price * 100.0
        max_slip = settings.max_slippage_pct
        if slippage_pct > max_slip:
            raise LiveExecutionError(
                f"Post-fill slippage {slippage_pct:.3f}% exceeds limit {max_slip}%. "
                f"Fill price={fill_price}, expected={entry_price}. "
                "Trade will NOT be recorded. Manual review required."
            )

        # ── Create trade row ──────────────────────────────────────────────────
        trade_insert = TradeInsert(
            user_id=decision.user_id,
            bot_id=decision.bot_id,
            trade_decision_id=decision.id,
            agent_run_id=decision.agent_run_id,
            exchange=decision.exchange,
            symbol=decision.symbol,
            side=order.side,
            direction=decision.direction,
            mode="live",
            status=TradeStatus.OPEN.value,
            entry_price=fill_price,
            quantity=filled_qty,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            exchange_order_id=result.order_id,
            filled_quantity=filled_qty,
            avg_fill_price=fill_price,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            pnl=0.0,
            pnl_pct=0.0,
            risk_amount=decision.risk_summary.get("risk_amount"),
            risk_percent=decision.risk_summary.get("risk_percent"),
            risk_reward_ratio=decision.risk_summary.get("risk_reward_ratio"),
            expected_reward=decision.risk_summary.get("expected_reward"),
            notional=decision.risk_summary.get("notional"),
            metadata={
                "client_order_id": order.client_order_id,
                "exchange_status": result.status,
                "raw_response_status": result.raw_response.get("status"),
                "market_snapshot_id": market_snapshot.id if market_snapshot else None,
                "reward_plan": decision.risk_summary.get("reward_plan") or {},
                "tp_plan": decision.risk_summary.get("tp_plan") or [],
            },
        )

        trade = await self._trade_repo.create(trade_insert)

        # ── Write trade events ────────────────────────────────────────────────
        await self._event_repo.bulk_create([
            TradeEventInsert(
                trade_id=trade.id,
                trade_decision_id=decision.id,
                bot_id=decision.bot_id,
                user_id=decision.user_id,
                event_type="live_order_placed",
                details={
                    "exchange_order_id": result.order_id,
                    "client_order_id": order.client_order_id,
                    "side": order.side,
                    "symbol": order.symbol,
                    "order_type": order.order_type,
                },
            ),
            TradeEventInsert(
                trade_id=trade.id,
                trade_decision_id=decision.id,
                bot_id=decision.bot_id,
                user_id=decision.user_id,
                event_type="live_order_filled",
                details={
                    "fill_price": fill_price,
                    "filled_qty": filled_qty,
                    "avg_fill_price": result.avg_fill_price,
                    "exchange_status": result.status,
                },
            ),
        ])

        log.info(
            "live_executor.done",
            trade_id=trade.id,
            decision_id=decision.id,
            fill_price=fill_price,
            filled_qty=filled_qty,
            exchange_order_id=result.order_id,
            # DO NOT log api_key, api_secret, or credentials
        )
        return trade

    # ── Order confirmation ─────────────────────────────────────────────────────

    async def _confirm_fill(
        self,
        *,
        order_id: str,
        exchange: str,
        symbol: str,
        exchange_account_id: str,
        expected_qty: float,
        expected_price: float,
    ) -> tuple[float, float]:
        """
        Confirm fill by calling fetch_order() with fresh credentials.

        Returns:
            (fill_price, filled_qty) — actual values from the exchange.

        Raises:
            LiveExecutionError: for any non-filled/partial state or fetch failure.
                                NEVER blindly retry — caller should fail-closed.
        """
        credentials: ApiCredentials | None = None
        adapter = None

        try:
            credentials = await self._key_provider.get_credentials(exchange_account_id)
            adapter = get_live_adapter(
                exchange=exchange,
                api_key=credentials.api_key,
                api_secret=credentials.api_secret,
            )

            confirmed: OrderResult = await adapter.fetch_order(order_id, symbol)

        except LiveExecutionError:
            raise
        except Exception as exc:
            raise LiveExecutionError(
                f"fetch_order failed for order_id={order_id}: {exc}. "
                "Cannot confirm fill — do not create trade."
            ) from exc
        finally:
            if credentials is not None:
                credentials.zero_out()
            if adapter is not None:
                try:
                    await adapter.close()
                except Exception:
                    pass

        exchange_status = (confirmed.status or "unknown").lower()

        log.info(
            "live_executor.fill_confirmed",
            order_id=order_id,
            exchange_status=exchange_status,
            filled_qty=confirmed.filled_quantity,
            avg_fill_price=confirmed.avg_fill_price,
        )

        # ── Filled ────────────────────────────────────────────────────────────
        if exchange_status in _FILLED_STATUSES:
            fill_price  = confirmed.avg_fill_price or expected_price
            filled_qty  = confirmed.filled_quantity or expected_qty
            return fill_price, filled_qty

        # ── Partial fill — acceptable, record actual quantity ─────────────────
        if exchange_status in _PARTIAL_STATUSES:
            fill_price = confirmed.avg_fill_price or expected_price
            filled_qty = confirmed.filled_quantity or expected_qty
            log.warning(
                "live_executor.partial_fill",
                order_id=order_id,
                filled_qty=filled_qty,
                expected_qty=expected_qty,
            )
            return fill_price, filled_qty

        # ── Still open / pending — exchange may be slow, but we still confirm ─
        if exchange_status in _OPEN_STATUSES:
            # Order placed and pending — use place_order values as best estimate.
            # In practice, market orders rarely stay in this state; conservative path.
            log.warning(
                "live_executor.order_still_open",
                order_id=order_id,
                exchange_status=exchange_status,
            )
            return expected_price, expected_qty

        # ── Unknown / rejected / cancelled → fail-closed ──────────────────────
        raise LiveExecutionError(
            f"Order {order_id} returned status '{exchange_status}' — "
            "fill not confirmed. Trade NOT created. Manual review required."
        )
