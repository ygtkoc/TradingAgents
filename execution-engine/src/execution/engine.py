"""
ExecutionEngine - orchestrates the full trade execution pipeline.

Pipeline per decision:
  0. Load context: bot, user_settings, exchange_account, market_snapshot
  1. Resolve paper/shadow/live execution path
  2. Apply live-only guards when execution path is live
  3. Idempotency check
  4. Risk guard
  5. Order build
  6. Execute via Paper / Shadow / LiveExecutor
  7. Mark trade_decisions execution_status
  8. Write audit log and notifications

Paper execution must never depend on exchange accounts or API permissions.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from src.config import settings
from src.db.models import (
    AuditLogInsert,
    Bot,
    ExchangeAccount,
    MarketSnapshot,
    RiskLogInsert,
    SecurityLogInsert,
    SeverityLevel,
    Trade,
    TradeDecision,
    UserSettings,
)
from src.db.repositories import (
    AuditLogRepository,
    BotRepository,
    PlatformSettingsRepository,
    RiskLogRepository,
    SecurityLogRepository,
    TradeDecisionRepository,
)
from src.execution.idempotency import IdempotencyChecker
from src.execution.live_executor import LiveExecutionError, LiveExecutor
from src.execution.order_builder import OrderBuildError, OrderBuilder
from src.execution.paper_executor import PaperExecutor
from src.execution.reward_plan import final_take_profit, normalize_reward_plan
from src.execution.shadow_executor import ShadowExecutor
from src.guards.risk_guard import RiskExecutionGuard
from src.guards.security_guard import SecurityExecutionGuard
from src.logging_config import get_logger
from src.services.market_data import MarketDataService
from src.services.futures_metadata import FuturesMetadataService
from src.services.notifications import NotificationService
from src.services.paper_account import PaperAccountService
from src.services.recovery import RecoveryService

log = get_logger(__name__)


class ExecutionEngine:
    """
    Runs the full execution pipeline for a single trade decision.

    Instantiate once per worker process and call run() for each claimed decision.
    """

    def __init__(self) -> None:
        self._decision_repo = TradeDecisionRepository()
        self._bot_repo = BotRepository()
        self._platform_repo = PlatformSettingsRepository()
        self._audit_log = AuditLogRepository()
        self._risk_log = RiskLogRepository()
        self._security_log = SecurityLogRepository()
        self._security_guard = SecurityExecutionGuard()
        self._risk_guard = RiskExecutionGuard()
        self._idempotency = IdempotencyChecker()
        self._market_data = MarketDataService()
        self._futures_metadata = FuturesMetadataService()
        self._notifications = NotificationService()
        self._recovery = RecoveryService()
        self._paper_account = PaperAccountService()
        self._paper_executor = PaperExecutor()
        self._shadow_executor = ShadowExecutor()
        self._live_executor = LiveExecutor()

    async def run(self, decision: TradeDecision) -> None:
        """
        Execute one trade decision through the full pipeline.

        Never raises. All errors are caught, logged, and the decision is
        marked failed.
        """
        log.info(
            "engine.pipeline_start",
            decision_id=decision.id,
            symbol=decision.symbol,
            mode=decision.mode,
            final_decision=decision.final_decision,
            approval_status=decision.approval_status,
        )

        try:
            await asyncio.wait_for(
                self._run_pipeline(decision),
                timeout=settings.pipeline_timeout_seconds,
            )
        except asyncio.TimeoutError:
            msg = f"Pipeline timed out after {settings.pipeline_timeout_seconds}s"
            log.error("engine.pipeline_timeout", decision_id=decision.id, message=msg)
            await self._fail(decision, msg)
        except Exception as exc:
            log.error(
                "engine.pipeline_unhandled_error",
                decision_id=decision.id,
                error=str(exc)[:400],
                exc_info=True,
            )
            await self._fail(decision, str(exc)[:400])

    async def _run_pipeline(self, decision: TradeDecision) -> None:
        bot, user_settings, exchange_account, market_snapshot = await self._load_context(
            decision
        )
        execution_mode = self._resolve_execution_mode(decision, bot)
        is_live = execution_mode == "live"

        log.info(
            f"execution.path.{execution_mode}",
            decision_id=decision.id,
            decision_mode=decision.mode,
            bot_mode=(bot.mode if bot else None),
        )

        if is_live and not settings.enable_live_execution:
            reason = "ENABLE_LIVE_EXECUTION=false - live trading not enabled"
            log.warning(
                "execution.skip.live_guard",
                decision_id=decision.id,
                reason=reason,
            )
            await self._security_log.create(
                SecurityLogInsert(
                    user_id=decision.user_id,
                    event_type="live_execution_gate_blocked",
                    severity=SeverityLevel.HIGH.value,
                    source="execution_engine",
                    message=(
                        "Live trade decision reached execution engine but "
                        "ENABLE_LIVE_EXECUTION=false. Decision skipped."
                    ),
                    metadata={"decision_id": decision.id},
                )
            )
            await self._notifications.live_gate_blocked(decision=decision)
            await self._decision_repo.mark_skipped(decision.id, reason)
            return

        try:
            platform_settings = await self._platform_repo.get()
        except Exception as exc:
            log.error("engine.platform_settings_load_failed", error=str(exc)[:200])
            from src.db.models import PlatformSettings

            platform_settings = PlatformSettings()

        portfolio_value_usd = await self._get_portfolio_value(
            exchange_account=exchange_account,
            user_settings=user_settings,
            market_snapshot=market_snapshot,
            decision=decision,
            execution_mode=execution_mode,
        )
        max_leverage = await self._resolve_max_leverage(
            decision=decision,
            bot=bot,
            execution_mode=execution_mode,
        )
        self._enrich_missing_risk_summary(
            decision=decision,
            bot=bot,
            market_snapshot=market_snapshot,
            portfolio_value_usd=portfolio_value_usd,
            user_settings=user_settings,
            max_leverage=max_leverage,
        )

        critical_event_count = await self._decision_repo.count_critical_security_events(
            decision.user_id
        )
        sec_result = self._security_guard.check(
            decision=decision,
            bot=bot,
            user_settings=user_settings,
            exchange_account=exchange_account,
            critical_security_event_count=critical_event_count,
            platform_settings=platform_settings,
        )
        if sec_result.blocked:
            await self._security_log.create(
                SecurityLogInsert(
                    user_id=decision.user_id,
                    event_type="security_guard_blocked_execution",
                    severity=SeverityLevel.CRITICAL.value,
                    source="execution_engine",
                    message=f"Security guard blocked: {sec_result.reason[:400]}",
                    metadata={
                        "decision_id": decision.id,
                        "failed_checks": [
                            {"name": c.name, "message": c.message}
                            for c in sec_result.failed_checks
                        ],
                    },
                )
            )
            await self._notifications.trade_skipped(
                decision=decision, reason=sec_result.reason
            )
            await self._decision_repo.mark_skipped(decision.id, sec_result.reason[:500])
            return

        existing_trade = await self._idempotency.find_existing_trade(decision.id)
        if existing_trade is not None:
            await self._recovery.recover_existing_trade(
                decision=decision, existing_trade=existing_trade
            )
            await self._notifications.trade_executed(
                decision=decision, trade=existing_trade
            )
            return

        entry_price_estimate = self._estimate_entry_price(decision, market_snapshot)
        quantity_estimate = self._estimate_quantity(
            decision, entry_price_estimate, portfolio_value_usd
        )

        open_trade_count = await self._bot_repo.count_open_trades(decision.bot_id)
        daily_loss_usd = 0.0

        risk_result = self._risk_guard.check(
            decision=decision,
            bot=bot,
            user_settings=user_settings,
            open_trade_count=open_trade_count,
            market_snapshot=market_snapshot,
            portfolio_value_usd=portfolio_value_usd,
            daily_loss_usd=daily_loss_usd,
            quantity=quantity_estimate,
            entry_price=entry_price_estimate,
        )
        if risk_result.blocked:
            await self._risk_log.create(
                RiskLogInsert(
                    user_id=decision.user_id,
                    bot_id=decision.bot_id,
                    trade_decision_id=decision.id,
                    risk_type="execution_guard",
                    severity=SeverityLevel.HIGH.value,
                    triggered=True,
                    message=f"Risk guard blocked execution: {risk_result.reason[:400]}",
                    metadata={
                        "decision_id": decision.id,
                        "failed_checks": [
                            {"name": c.name, "message": c.message}
                            for c in risk_result.failed_checks
                        ],
                    },
                )
            )
            await self._notifications.trade_skipped(
                decision=decision, reason=risk_result.reason
            )
            await self._decision_repo.mark_skipped(decision.id, risk_result.reason[:500])
            return

        order_builder = OrderBuilder(portfolio_value_usd=portfolio_value_usd)
        try:
            order, entry_price = order_builder.build(decision, market_snapshot)
        except OrderBuildError as exc:
            await self._fail(decision, f"Order build failed: {exc}")
            return

        trade = await self._dispatch_execution(
            decision=decision,
            bot=bot,
            execution_mode=execution_mode,
            exchange_account=exchange_account,
            order=order,
            entry_price=entry_price,
            market_snapshot=market_snapshot,
        )
        if trade is None:
            return

        await self._decision_repo.mark_executed(decision.id, trade.id)

        await self._audit_log.create(
            AuditLogInsert(
                user_id=decision.user_id,
                action="trade_executed",
                record_id=trade.id,
                table_name="trades",
                source="execution_engine",
                metadata={
                    "decision_id": decision.id,
                    "mode": trade.mode,
                    "symbol": decision.symbol,
                    "side": order.side,
                    "quantity": trade.quantity,
                    "entry_price": trade.entry_price,
                },
            )
        )

        await self._notifications.trade_executed(decision=decision, trade=trade)

        log.info(
            "execution.completed",
            decision_id=decision.id,
            trade_id=trade.id,
            mode=trade.mode,
            symbol=trade.symbol,
        )

    async def _load_context(
        self, decision: TradeDecision
    ) -> tuple[
        Optional[Bot],
        Optional[UserSettings],
        Optional[ExchangeAccount],
        Optional[MarketSnapshot],
    ]:
        bot_task = asyncio.create_task(self._bot_repo.get_bot(decision.bot_id))
        settings_task = asyncio.create_task(
            self._bot_repo.get_user_settings(decision.user_id)
        )
        snapshot_task = asyncio.create_task(
            self._market_data.get_snapshot(decision.exchange, decision.symbol)
        )

        bot, user_settings, market_snapshot = await asyncio.gather(
            bot_task, settings_task, snapshot_task, return_exceptions=True
        )

        exchange_account: Optional[ExchangeAccount] = None
        if isinstance(bot, Exception):
            log.error("engine.load_bot_failed", error=str(bot))
            bot = None
        if isinstance(user_settings, Exception):
            log.error("engine.load_user_settings_failed", error=str(user_settings))
            user_settings = None
        if isinstance(market_snapshot, Exception):
            log.error("engine.load_market_snapshot_failed", error=str(market_snapshot))
            market_snapshot = None

        account_id = (bot.exchange_account_id if bot else None) or decision.metadata.get(
            "exchange_account_id"
        )
        if account_id:
            try:
                exchange_account = await self._bot_repo.get_exchange_account(account_id)
            except Exception as exc:
                log.error("engine.load_exchange_account_failed", error=str(exc))
                exchange_account = None

        return bot, user_settings, exchange_account, market_snapshot

    def _resolve_execution_mode(
        self,
        decision: TradeDecision,
        bot: Optional[Bot],
    ) -> str:
        if decision.mode == "paper":
            return "paper"
        if bot and bot.mode == "paper":
            return "paper"
        if decision.mode == "shadow":
            return "shadow"
        return "live"

    async def _get_portfolio_value(
        self,
        *,
        exchange_account: Optional[ExchangeAccount],
        user_settings: Optional[UserSettings],
        market_snapshot: Optional[MarketSnapshot],
        decision: TradeDecision,
        execution_mode: str,
    ) -> float:
        if execution_mode in ("paper", "shadow"):
            acct = await self._paper_account.get_account(decision.user_id)
            if acct:
                for key in ("equity", "balance", "available_balance", "starting_balance"):
                    try:
                        value = float(acct.get(key) or 0)
                    except (TypeError, ValueError):
                        value = 0.0
                    if value > 0:
                        return value
            log.error(
                "execution.paper_account_missing_for_sizing",
                decision_id=decision.id,
                user_id=decision.user_id,
                execution_mode=execution_mode,
            )
            return 0.0
        return settings.paper_portfolio_value_usd

    def _estimate_entry_price(
        self,
        decision: TradeDecision,
        market_snapshot: Optional[MarketSnapshot],
    ) -> float:
        risk = decision.risk_summary or {}
        if risk.get("entry_price"):
            try:
                return float(risk["entry_price"])
            except (TypeError, ValueError):
                pass
        if market_snapshot:
            return market_snapshot.close_price
        return 0.0

    def _estimate_quantity(
        self,
        decision: TradeDecision,
        entry_price: float,
        portfolio_value: float,
    ) -> float:
        risk = decision.risk_summary or {}
        if risk.get("quantity"):
            try:
                return float(risk["quantity"])
            except (TypeError, ValueError):
                pass
        if entry_price > 0 and portfolio_value > 0:
            size_pct = float(risk.get("position_size_pct", 1.0))
            return (portfolio_value * size_pct / 100.0) / entry_price
        return 0.0

    async def _resolve_max_leverage(
        self,
        *,
        decision: TradeDecision,
        bot: Optional[Bot],
        execution_mode: str,
    ) -> float:
        if execution_mode not in ("paper", "shadow"):
            return 1.0

        metadata = (bot.metadata if bot else {}) or {}
        configured = self._get_configured_leverage(metadata, decision.symbol)
        if configured:
            return configured

        if str(metadata.get("trading_system") or "") == "futures_trading":
            return await self._futures_metadata.max_leverage(
                decision.exchange,
                decision.symbol,
            )
        return 1.0

    @staticmethod
    def _get_configured_leverage(metadata: dict, symbol: str) -> Optional[float]:
        def as_float(value) -> Optional[float]:
            try:
                parsed = float(value)
                return parsed if parsed > 0 else None
            except (TypeError, ValueError):
                return None

        by_symbol = metadata.get("max_leverage_by_symbol")
        if isinstance(by_symbol, dict):
            normalized = symbol.replace("/", "").upper()
            for key in (symbol, symbol.upper(), normalized):
                value = as_float(by_symbol.get(key))
                if value:
                    return value
        return as_float(
            metadata.get("max_leverage")
            or metadata.get("leverage")
            or metadata.get("paper_max_leverage")
        )

    def _enrich_missing_risk_summary(
        self,
        *,
        decision: TradeDecision,
        bot: Optional[Bot],
        market_snapshot: Optional[MarketSnapshot],
        portfolio_value_usd: float,
        user_settings: Optional[UserSettings] = None,
        max_leverage: float = 1.0,
    ) -> None:
        if bot is None:
            return

        risk = dict(decision.risk_summary or {})
        entry_price = self._estimate_entry_price(decision, market_snapshot)
        if entry_price <= 0 or portfolio_value_usd <= 0:
            return

        def num(value, fallback: Optional[float] = None) -> Optional[float]:
            try:
                if value is None:
                    return fallback
                return float(value)
            except (TypeError, ValueError):
                return fallback

        is_short = decision.final_decision == "open_short" or decision.direction == "short"
        metadata = bot.metadata or {}
        stop_loss_pct = num(metadata.get("stop_loss_pct"), 2.0)
        max_reward_r = num(
            getattr(user_settings, "max_reward_r", None),
            num(metadata.get("max_reward_r"), 5.0),
        ) or 5.0
        min_reward_r = num(
            getattr(user_settings, "min_reward_r", None),
            num(metadata.get("min_reward_r"), 1.5),
        ) or 1.5

        if not risk.get("entry_price"):
            risk["entry_price"] = entry_price

        if not risk.get("stop_loss") and stop_loss_pct and stop_loss_pct > 0:
            distance = entry_price * (stop_loss_pct / 100.0)
            risk["stop_loss"] = entry_price + distance if is_short else entry_price - distance

        risk_pct = num(
            getattr(user_settings, "default_risk_per_trade_pct", None),
            None,
        )
        if risk_pct is None or risk_pct <= 0:
            risk_pct = num(bot.risk_value if bot.risk_model == "percentage" else bot.risk_per_trade_pct)
        if risk_pct is None or risk_pct <= 0:
            risk_pct = 2.0
        max_risk_amount = portfolio_value_usd * (risk_pct / 100.0)

        stop_loss = num(risk.get("stop_loss"))
        stop_distance = abs(entry_price - stop_loss) if stop_loss else 0.0
        risk_qty = max_risk_amount / stop_distance if stop_distance > 0 else None
        is_futures_profile = str(metadata.get("trading_system") or "") == "futures_trading"
        leverage = max(1.0, float(max_leverage or 1.0)) if is_futures_profile else 1.0
        max_position_pct = 100.0 * leverage
        max_position_qty = (portfolio_value_usd * (max_position_pct / 100.0)) / entry_price

        qty_candidates = [q for q in (risk_qty, max_position_qty) if q and q > 0]
        if not risk.get("quantity") and qty_candidates:
            quantity = min(qty_candidates)
            notional = quantity * entry_price
            margin_required = notional / leverage
            risk["quantity"] = round(quantity, 8)
            risk["risk_amount"] = round(stop_distance * quantity, 8) if stop_distance > 0 else max_risk_amount
            risk["risk_percent"] = round((float(risk["risk_amount"]) / portfolio_value_usd) * 100.0, 6)
            risk["position_size_pct"] = round((notional / portfolio_value_usd) * 100.0, 6)
            risk["notional"] = round(notional, 8)
            risk["leverage"] = round(leverage, 4)
            risk["margin_required"] = round(margin_required, 8)
            risk["margin_percent"] = round((margin_required / portfolio_value_usd) * 100.0, 6)
            risk["sizing_model"] = "wallet_risk_max_leverage"
        else:
            risk.setdefault("risk_amount", max_risk_amount)
            risk.setdefault("risk_percent", risk_pct)

        stop_loss = num(risk.get("stop_loss"))
        if stop_loss and stop_loss > 0:
            reward_plan = normalize_reward_plan(
                risk_summary=risk,
                entry_price=entry_price,
                stop_loss=stop_loss,
                direction="short" if is_short else "long",
                max_reward_r=max_reward_r,
                min_reward_r=min_reward_r,
            )
            if reward_plan:
                selected_r = float(reward_plan["selected_reward_r"])
                take_profit = final_take_profit(reward_plan)
                risk["reward_plan"] = reward_plan
                risk["tp_plan"] = reward_plan["levels"]
                risk["risk_reward_ratio"] = selected_r
                risk["expected_reward"] = (
                    float(risk.get("risk_amount") or max_risk_amount) * selected_r
                )
                if take_profit:
                    risk["take_profit"] = take_profit

        risk.setdefault(
            "risk_reward_ratio",
            min(max_reward_r, num(bot.risk_reward_ratio, 2.0) or 2.0),
        )
        decision.risk_summary = risk

    async def _dispatch_execution(
        self,
        *,
        decision: TradeDecision,
        bot: Optional[Bot],
        execution_mode: str,
        exchange_account: Optional[ExchangeAccount],
        order,
        entry_price: float,
        market_snapshot: Optional[MarketSnapshot],
    ) -> Optional[Trade]:
        try:
            if execution_mode == "paper":
                return await self._paper_executor.execute(
                    decision=decision,
                    bot=bot,
                    order=order,
                    entry_price=entry_price,
                    market_snapshot=market_snapshot,
                )

            if execution_mode == "shadow":
                return await self._shadow_executor.execute(
                    decision=decision,
                    bot=bot,
                    order=order,
                    entry_price=entry_price,
                    market_snapshot=market_snapshot,
                )

            if execution_mode == "live":
                if exchange_account is None:
                    await self._fail(decision, "No exchange account for live execution")
                    return None
                return await self._live_executor.execute(
                    decision=decision,
                    bot=bot,
                    exchange_account=exchange_account,
                    order=order,
                    entry_price=entry_price,
                    market_snapshot=market_snapshot,
                )
        except LiveExecutionError as exc:
            await self._fail(decision, f"Live execution error: {exc}")
            return None
        except Exception as exc:
            await self._fail(decision, f"Executor error ({execution_mode}): {exc}")
            return None

        await self._fail(decision, f"Unknown execution mode: {execution_mode}")
        return None

    async def _fail(self, decision: TradeDecision, error: str) -> None:
        try:
            log.error(
                "execution.failed",
                decision_id=decision.id,
                error=error[:200],
            )
            await self._decision_repo.mark_failed(decision.id, error)
            await self._notifications.trade_failed(decision=decision, error=error)
        except Exception as exc:
            log.error(
                "engine.mark_failed_error",
                decision_id=decision.id,
                original_error=error[:200],
                meta_error=str(exc)[:200],
            )
