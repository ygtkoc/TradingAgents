"""
LifecycleEngine — orchestrates position monitoring for a single trade.

Pipeline per claimed trade:
  0.  Detect stuck 'closing' state → recovery
  1.  Load context (bot, user_settings, exchange_account, market_snapshot, platform_settings)
  2.  Determine current_price
  3.  LifecycleSecurityGuard.check()  — block on any failure
  4.  Evaluate all lifecycle triggers (priority order):
        a. Emergency conditions
        b. Stop-loss
        c. Take-profit
        d. Trailing stop
  5.  Apply highest-priority action:
        HOLD / UPDATE_PNL / UPDATE_TRAILING_STOP → update + release claim
        PAUSE_MONITORING                          → release claim (stop processing)
        MARK_NEEDS_RECONCILIATION                 → mark + release
        CLOSE_*                                   → run close flow
  6.  Write trade events, risk logs, security logs, audit logs
  7.  Release claim

Fail-closed invariants:
  - Paper/shadow NEVER call real exchange
  - Live close requires ENABLE_LIVE_CLOSE=true + platform_settings.emergency_close_enabled (for emergency)
  - Unknown close order result → needs_reconciliation, never blind retry
  - Any exception → mark failed, write audit log
"""
from __future__ import annotations

import asyncio
import hashlib
from typing import Optional

from src.config import settings
from src.db.models import (
    AuditLogInsert,
    Bot,
    ExchangeAccount,
    LifecycleStatus,
    MarketSnapshot,
    PlatformSettings,
    RiskLogInsert,
    SecurityLogInsert,
    SeverityLevel,
    Trade,
    TradeEventInsert,
    TradeUpdateLifecycle,
    UserSettings,
)
from src.db.repositories import (
    AuditLogRepository,
    ContextRepository,
    PlatformSettingsRepository,
    RiskLogRepository,
    SecurityLogRepository,
    TradeEventRepository,
    TradeLifecycleRepository,
)
from src.exchanges.base import ExchangeAdapter, OrderRequest, OrderResult
from src.exchanges.factory import get_live_adapter, get_paper_adapter
from src.guards.lifecycle_risk_guard import LifecycleRiskGuard
from src.guards.lifecycle_security_guard import LifecycleSecurityGuard
from src.keys.key_provider import ApiCredentials, KeyProvider
from src.lifecycle.action import (
    ActionType,
    LifecycleAction,
    highest_priority,
    hold,
    update_pnl,
)
from src.lifecycle.emergency import check_emergency
from src.lifecycle.pnl import calculate_realized_pnl, calculate_unrealized_pnl, pnl_percentage
from src.lifecycle.pnl_limits import check_pnl_stop_loss, check_pnl_take_profit
from src.lifecycle.reconciliation import ReconciliationResult, reconcile_trade
from src.lifecycle.scaled_take_profit import (
    check_scaled_take_profit,
    mark_level_hit,
    next_take_profit_after_tp,
    next_stop_after_tp,
)
from src.lifecycle.stop_loss import check_stop_loss
from src.lifecycle.take_profit import check_take_profit
from src.lifecycle.trailing_stop import check_trailing_stop
from src.logging_config import get_logger
from src.services.market_data import MarketDataService
from src.services.notifications import NotificationService
from src.services.paper_account import PaperAccountService
from src.services.recovery import RecoveryService
from src.utils.time import utcnow_iso

log = get_logger(__name__)

# Exchange statuses that confirm a close order was filled
_CLOSE_FILLED_STATUSES  = frozenset({"filled", "closed", "done"})
_CLOSE_PARTIAL_STATUSES = frozenset({"partially_filled", "partial"})
_CLOSE_DEAD_STATUSES    = frozenset({"cancelled", "canceled", "rejected", "expired"})


class LifecycleEngine:
    """
    Runs the full lifecycle pipeline for a single open trade.

    Instantiate once per worker process. Call run() for each claimed trade.
    """

    def __init__(self) -> None:
        self._lifecycle_repo   = TradeLifecycleRepository()
        self._context_repo     = ContextRepository()
        self._platform_repo    = PlatformSettingsRepository()
        self._event_repo       = TradeEventRepository()
        self._risk_log         = RiskLogRepository()
        self._security_log     = SecurityLogRepository()
        self._audit_log        = AuditLogRepository()
        self._security_guard   = LifecycleSecurityGuard()
        self._risk_guard       = LifecycleRiskGuard()
        self._market_data      = MarketDataService()
        self._notifications    = NotificationService()
        self._paper_account    = PaperAccountService()
        self._recovery         = RecoveryService()
        self._key_provider     = KeyProvider()

    async def run(self, trade: Trade) -> None:
        """
        Execute one lifecycle cycle for a claimed trade.

        Never raises. All errors are caught, logged, and the trade is
        released or marked failed/needs_reconciliation.
        """
        log.info(
            "lifecycle.pipeline_start",
            trade_id=trade.id,
            symbol=trade.symbol,
            mode=trade.mode,
            direction=trade.direction,
            lifecycle_status=trade.lifecycle_status,
        )

        try:
            await asyncio.wait_for(
                self._run_pipeline(trade),
                timeout=settings.order_confirmation_timeout_seconds + 30,
            )
        except asyncio.TimeoutError:
            msg = f"Lifecycle pipeline timed out"
            log.error("lifecycle.timeout", trade_id=trade.id)
            if trade.is_live:
                await self._lifecycle_repo.mark_needs_reconciliation(trade.id, msg)
            else:
                await self._event_repo.create(TradeEventInsert(
                    trade_id=trade.id,
                    bot_id=trade.bot_id,
                    user_id=trade.user_id,
                    event_type="lifecycle_timeout_released",
                    details={"reason": msg, "mode": trade.mode},
                ))
                await self._lifecycle_repo.release_claim(trade.id)
        except Exception as exc:
            log.error(
                "lifecycle.unhandled_error",
                trade_id=trade.id,
                error=str(exc)[:400],
                exc_info=True,
            )
            await self._fail(trade, str(exc)[:400])

    async def _run_pipeline(self, trade: Trade) -> None:
        """Inner pipeline — may raise; run() catches everything."""

        # ── Step 0: Detect stuck 'closing' state ─────────────────────────────
        if trade.lifecycle_status == LifecycleStatus.CLOSING.value:
            log.warning("lifecycle.found_stuck_closing", trade_id=trade.id)
            await self._recovery.handle_stuck_closing(trade)
            return

        # ── Step 1: Load context ──────────────────────────────────────────────
        if trade.mode in ("paper", "shadow") and trade.status == "open":
            market_snapshot = await self._market_data.get_snapshot(trade.exchange, trade.symbol)
            current_price = self._resolve_price(trade, market_snapshot)
            if current_price <= 0:
                await self._event_repo.create(TradeEventInsert(
                    trade_id=trade.id,
                    bot_id=trade.bot_id,
                    user_id=trade.user_id,
                    event_type="price_checked",
                    details={"error": "No valid price available", "current_price": current_price},
                ))
                await self._lifecycle_repo.release_claim(trade.id)
                return

            protective_action = self._evaluate_protective_triggers(
                trade=trade,
                current_price=current_price,
                market_snapshot=market_snapshot,
            )
            if protective_action.action_type in (
                ActionType.CLOSE_STOP_LOSS,
                ActionType.CLOSE_TAKE_PROFIT,
            ):
                log.info(
                    "lifecycle.fast_protective_action_selected",
                    trade_id=trade.id,
                    action=protective_action.action_type.name,
                    reason=protective_action.reason[:200],
                )
                await self._apply_action(
                    trade=trade,
                    action=protective_action,
                    current_price=current_price,
                    bot=None,
                    exchange_account=None,
                    market_snapshot=market_snapshot,
                    platform_settings=PlatformSettings(),
                )
                return

        ps, bot, user_settings, exchange_account, market_snapshot = (
            await self._load_context(trade)
        )

        # ── Step 2: Determine current price ───────────────────────────────────
        current_price = self._resolve_price(trade, market_snapshot)
        if current_price <= 0:
            await self._event_repo.create(TradeEventInsert(
                trade_id=trade.id,
                bot_id=trade.bot_id,
                user_id=trade.user_id,
                event_type="price_checked",
                details={"error": "No valid price available", "current_price": current_price},
            ))
            await self._lifecycle_repo.release_claim(trade.id)
            return

        await self._event_repo.create(TradeEventInsert(
            trade_id=trade.id,
            bot_id=trade.bot_id,
            user_id=trade.user_id,
            event_type="price_checked",
            details={"current_price": current_price, "mode": trade.mode},
        ))

        # ── Step 3: Security guard ────────────────────────────────────────────
        sec_result = self._security_guard.check(
            trade=trade,
            bot=bot,
            user_settings=user_settings,
            exchange_account=exchange_account,
            platform_settings=ps,
            critical_security_event_count=await self._lifecycle_repo.count_critical_security_events(
                trade.user_id
            ),
        )

        if sec_result.blocked:
            await self._security_log.create(SecurityLogInsert(
                user_id=trade.user_id,
                event_type="live_close_blocked",
                severity=SeverityLevel.HIGH.value,
                source="position_engine",
                message=f"Security guard blocked lifecycle action: {sec_result.reason[:300]}",
                metadata={"trade_id": trade.id, "failed_checks": [
                    {"name": c.name, "message": c.message}
                    for c in sec_result.failed_checks
                ]},
            ))
            await self._lifecycle_repo.release_claim(trade.id)
            return

        # ── Step 3.5: Reconciliation (live trades + needs_reconciliation) ────
        # Runs BEFORE SL/TP/trailing to ensure DB and exchange agree.
        # NEVER auto-closes: any anomaly → MARK_NEEDS_RECONCILIATION.
        needs_recon = (
            trade.lifecycle_status == LifecycleStatus.NEEDS_RECONCILIATION.value
        )
        should_run_recon = needs_recon or (
            trade.is_live and trade.exchange_order_id is not None
        )

        if should_run_recon:
            recon = await self._run_reconciliation(trade, exchange_account)

            # If recon could not run at all (e.g. no exchange_account / paper
            # trade in needs_reconciliation), fail-closed: keep the
            # needs_reconciliation status, release the claim, do NOT trade.
            if recon is None:
                if needs_recon:
                    log.warning(
                        "lifecycle.cannot_reconcile_skipping_pipeline",
                        trade_id=trade.id,
                    )
                    await self._lifecycle_repo.release_claim(trade.id)
                    return
                # live trade with no account but order_id present — already
                # rare; fall through is unsafe, mark needs_reconciliation.
                await self._lifecycle_repo.mark_needs_reconciliation(
                    trade.id, "Cannot reconcile: missing exchange_account"
                )
                return

            recon_action = recon.action

            if recon_action.action_type != ActionType.HOLD:
                # Anomaly detected — handle, log, apply, STOP pipeline.
                await self._handle_reconciliation_result(
                    trade=trade,
                    recon=recon,
                    bot=bot,
                    exchange_account=exchange_account,
                    market_snapshot=market_snapshot,
                    platform_settings=ps,
                    current_price=current_price,
                )
                return  # MUST stop — do not run SL/TP/trailing on a drifted trade

            # recon returned HOLD (DB and exchange agree).
            if trade.status == "pending":
                log.info("lifecycle.pending_order_waiting", trade_id=trade.id)
                await self._lifecycle_repo.release_claim(trade.id)
                return

            # If trade was in needs_reconciliation status, do NOT auto-resume
            # SL/TP this cycle — release to idle and let the next cycle pick it
            # up cleanly. If it was a routine live spot-check, continue normally.
            if needs_recon:
                log.info(
                    "lifecycle.recon_resolved_consistent",
                    trade_id=trade.id,
                )
                await self._event_repo.create(TradeEventInsert(
                    trade_id=trade.id,
                    bot_id=trade.bot_id,
                    user_id=trade.user_id,
                    event_type="reconciliation_resolved",
                    details={"exchange_status": recon.exchange_status},
                ))
                await self._lifecycle_repo.release_claim(trade.id)
                return

        # ── Step 4: Evaluate lifecycle triggers ───────────────────────────────
        if trade.status == "pending":
            log.info("lifecycle.pending_order_waiting", trade_id=trade.id)
            await self._lifecycle_repo.release_claim(trade.id)
            return

        trade = await self._normalize_paper_wallet_risk(trade)

        action = await self._evaluate_triggers(
            trade=trade,
            current_price=current_price,
            bot=bot,
            user_settings=user_settings,
            exchange_account=exchange_account,
            platform_settings=ps,
            market_snapshot=market_snapshot,
        )

        log.info(
            "lifecycle.action_selected",
            trade_id=trade.id,
            action=action.action_type.name,
            reason=action.reason[:200],
        )

        # ── Step 5: Apply action ──────────────────────────────────────────────
        await self._apply_action(
            trade=trade,
            action=action,
            current_price=current_price,
            bot=bot,
            exchange_account=exchange_account,
            market_snapshot=market_snapshot,
            platform_settings=ps,
        )

    # ── Context loading ────────────────────────────────────────────────────────

    async def _load_context(
        self, trade: Trade
    ) -> tuple[
        PlatformSettings,
        Optional[Bot],
        Optional[UserSettings],
        Optional[ExchangeAccount],
        Optional[MarketSnapshot],
    ]:
        ps_task   = asyncio.create_task(self._platform_repo.get())
        bot_task  = asyncio.create_task(self._context_repo.get_bot(trade.bot_id))
        us_task   = asyncio.create_task(self._context_repo.get_user_settings(trade.user_id))
        snap_task = asyncio.create_task(
            self._market_data.get_snapshot(trade.exchange, trade.symbol)
        )

        ps, bot, user_settings, market_snapshot = await asyncio.gather(
            ps_task, bot_task, us_task, snap_task, return_exceptions=True
        )

        if isinstance(ps, Exception):
            log.error("lifecycle.load_platform_settings_failed", error=str(ps))
            ps = PlatformSettings()  # safe defaults: trading enabled
        if isinstance(bot, Exception):
            log.error("lifecycle.load_bot_failed", error=str(bot))
            bot = None
        if isinstance(user_settings, Exception):
            log.error("lifecycle.load_user_settings_failed", error=str(user_settings))
            user_settings = None
        if isinstance(market_snapshot, Exception):
            log.error("lifecycle.load_snapshot_failed", error=str(market_snapshot))
            market_snapshot = None

        # Exchange account (only needed for live trades)
        exchange_account = None
        if trade.is_live:
            account_id = (bot.exchange_account_id if bot else None)
            if account_id:
                try:
                    exchange_account = await self._context_repo.get_exchange_account(account_id)
                except Exception as exc:
                    log.error("lifecycle.load_exchange_account_failed", error=str(exc))

        return ps, bot, user_settings, exchange_account, market_snapshot

    def _resolve_price(
        self, trade: Trade, market_snapshot: Optional[MarketSnapshot]
    ) -> float:
        if market_snapshot and market_snapshot.close_price > 0:
            return market_snapshot.close_price
        # Fallback to entry price — only for paper/shadow, not live
        if not trade.is_live and trade.effective_entry_price > 0:
            return trade.effective_entry_price
        return 0.0

    # ── Trigger evaluation ────────────────────────────────────────────────────

    async def _evaluate_triggers(
        self,
        *,
        trade: Trade,
        current_price: float,
        bot: Optional[Bot],
        user_settings: Optional[UserSettings],
        exchange_account: Optional[ExchangeAccount],
        platform_settings: PlatformSettings,
        market_snapshot: Optional[MarketSnapshot],
    ) -> LifecycleAction:
        actions: list[LifecycleAction] = []

        # Emergency check (highest priority)
        sec_event_count = await self._lifecycle_repo.count_critical_security_events(trade.user_id)
        emergency = check_emergency(
            trade=trade,
            bot=bot,
            user_settings=user_settings,
            exchange_account=exchange_account,
            platform_settings=platform_settings,
            critical_security_event_count=sec_event_count,
            current_price=current_price,
        )
        actions.append(emergency)

        # Compute P&L once so price-level and dollar-level triggers use the
        # same current price for this lifecycle cycle.
        pnl = calculate_unrealized_pnl(trade, current_price)

        high_price = market_snapshot.high_price if market_snapshot else current_price
        low_price = market_snapshot.low_price if market_snapshot else current_price

        # Stop-loss
        actions.append(
            check_stop_loss(
                trade,
                current_price,
                high_price=high_price,
                low_price=low_price,
            )
        )
        actions.append(check_pnl_stop_loss(trade, current_price, pnl))

        # Take-profit
        actions.append(
            check_scaled_take_profit(
                trade,
                current_price,
                high_price=high_price,
                low_price=low_price,
            )
        )
        actions.append(
            check_take_profit(
                trade,
                current_price,
                high_price=high_price,
                low_price=low_price,
            )
        )
        actions.append(check_pnl_take_profit(trade, current_price, pnl))

        # Trailing stop
        trailing_pct = None
        if bot:
            trailing_pct = bot.trailing_stop_pct or bot.metadata.get("trailing_stop_pct")
        actions.append(check_trailing_stop(trade, current_price, trailing_pct))

        # Unrealized P&L update (lowest priority trigger)
        actions.append(update_pnl(pnl))

        return highest_priority(actions)

    # ── Action application ────────────────────────────────────────────────────

    def _evaluate_protective_triggers(
        self,
        *,
        trade: Trade,
        current_price: float,
        market_snapshot: Optional[MarketSnapshot],
    ) -> LifecycleAction:
        """Evaluate stop-loss and take-profit before slower advisory checks."""
        actions: list[LifecycleAction] = [
            check_stop_loss(
                trade,
                current_price,
                high_price=current_price,
                low_price=current_price,
            ),
            check_scaled_take_profit(
                trade,
                current_price,
                high_price=current_price,
                low_price=current_price,
            ),
            check_take_profit(
                trade,
                current_price,
                high_price=current_price,
                low_price=current_price,
            ),
        ]
        return highest_priority(actions)

    async def _apply_action(
        self,
        *,
        trade: Trade,
        action: LifecycleAction,
        current_price: float,
        bot: Optional[Bot],
        exchange_account: Optional[ExchangeAccount],
        market_snapshot: Optional[MarketSnapshot],
        platform_settings: PlatformSettings,
    ) -> None:
        atype = action.action_type

        if atype == ActionType.HOLD:
            await self._apply_hold(trade)

        elif atype == ActionType.UPDATE_PNL:
            await self._apply_update_pnl(trade, action)

        elif atype == ActionType.UPDATE_TRAILING_STOP:
            await self._apply_update_trailing_stop(trade, action)

        elif atype == ActionType.PAUSE_MONITORING:
            await self._apply_pause(trade, action)

        elif atype == ActionType.MARK_NEEDS_RECONCILIATION:
            await self._apply_needs_reconciliation(trade, action)

        elif atype in (
            ActionType.CLOSE_STOP_LOSS,
            ActionType.CLOSE_TAKE_PROFIT,
            ActionType.CLOSE_TRAILING_STOP,
            ActionType.CLOSE_EMERGENCY,
        ):
            await self._apply_close(
                trade=trade,
                action=action,
                current_price=current_price,
                exchange_account=exchange_account,
                market_snapshot=market_snapshot,
                platform_settings=platform_settings,
                is_emergency=(atype == ActionType.CLOSE_EMERGENCY),
            )
        else:
            log.warning(
                "lifecycle.unknown_action",
                trade_id=trade.id,
                action=str(atype),
            )
            await self._lifecycle_repo.release_claim(trade.id)

    # ── Action handlers ────────────────────────────────────────────────────────

    async def _apply_hold(self, trade: Trade) -> None:
        await self._lifecycle_repo.release_claim(trade.id)

    async def _apply_update_pnl(self, trade: Trade, action: LifecycleAction) -> None:
        pnl = action.unrealized_pnl or 0.0
        pnl_pct = pnl_percentage(pnl, trade.effective_entry_price, trade.effective_quantity)
        await self._lifecycle_repo.update_trade(
            trade.id,
            TradeUpdateLifecycle(unrealized_pnl=pnl, pnl=pnl, pnl_pct=pnl_pct),
        )
        await self._event_repo.create(TradeEventInsert(
            trade_id=trade.id,
            bot_id=trade.bot_id,
            user_id=trade.user_id,
            event_type="pnl_updated",
            details={"unrealized_pnl": pnl, "pnl_pct": pnl_pct},
        ))
        if trade.mode == "paper":
            paper_account = getattr(self, "_paper_account", None)
            if paper_account is not None:
                await paper_account.sync_unrealized(user_id=trade.user_id)
        await self._lifecycle_repo.release_claim(trade.id)

    async def _apply_update_trailing_stop(
        self, trade: Trade, action: LifecycleAction
    ) -> None:
        update = TradeUpdateLifecycle(
            trailing_stop_price=action.new_trailing_stop,
            highest_price_seen=action.new_highest_seen,
            lowest_price_seen=action.new_lowest_seen,
            unrealized_pnl=action.unrealized_pnl,
        )
        await self._lifecycle_repo.update_trade(trade.id, update)
        await self._event_repo.create(TradeEventInsert(
            trade_id=trade.id,
            bot_id=trade.bot_id,
            user_id=trade.user_id,
            event_type="trailing_stop_updated",
            details={
                "trailing_stop_price": action.new_trailing_stop,
                "highest_price_seen":  action.new_highest_seen,
                "lowest_price_seen":   action.new_lowest_seen,
            },
        ))
        if trade.mode == "paper":
            paper_account = getattr(self, "_paper_account", None)
            if paper_account is not None:
                await paper_account.sync_unrealized(user_id=trade.user_id)
        await self._lifecycle_repo.release_claim(trade.id)

    async def _apply_pause(self, trade: Trade, action: LifecycleAction) -> None:
        log.warning(
            "lifecycle.monitoring_paused",
            trade_id=trade.id,
            reason=action.reason[:200],
        )
        await self._event_repo.create(TradeEventInsert(
            trade_id=trade.id,
            bot_id=trade.bot_id,
            user_id=trade.user_id,
            event_type="lifecycle_released",
            details={"reason": action.reason, "action": "pause_monitoring"},
        ))
        await self._lifecycle_repo.release_claim(trade.id)

    async def _apply_needs_reconciliation(
        self, trade: Trade, action: LifecycleAction
    ) -> None:
        await self._security_log.create(SecurityLogInsert(
            user_id=trade.user_id,
            event_type="reconciliation_required",
            severity=SeverityLevel.CRITICAL.value,
            source="position_engine",
            message=f"Trade {trade.id} needs reconciliation: {action.reason[:300]}",
            metadata={"trade_id": trade.id, **action.metadata},
        ))
        await self._event_repo.create(TradeEventInsert(
            trade_id=trade.id,
            bot_id=trade.bot_id,
            user_id=trade.user_id,
            event_type="reconciliation_required",
            details={"reason": action.reason, **action.metadata},
        ))
        await self._risk_log.create(RiskLogInsert(
            user_id=trade.user_id,
            bot_id=trade.bot_id,
            trade_id=trade.id,
            risk_type="reconciliation_required",
            severity=SeverityLevel.CRITICAL.value,
            triggered=True,
            message=action.reason[:400],
        ))
        await self._lifecycle_repo.mark_needs_reconciliation(trade.id, action.reason)
        await self._notifications.reconciliation_required(trade=trade, reason=action.reason)

    # ── Reconciliation ────────────────────────────────────────────────────────

    async def _normalize_paper_wallet_risk(self, trade: Trade) -> Trade:
        """Repair paper trades sized from the execution fallback portfolio."""
        if trade.mode != "paper":
            return trade

        try:
            risk_pct = float(trade.risk_percent or trade.metadata.get("risk_percent") or 0.0)
            current_risk = float(trade.risk_amount or 0.0)
        except (TypeError, ValueError):
            return trade
        if risk_pct <= 0 or current_risk <= 0:
            return trade

        paper_account = getattr(self, "_paper_account", None)
        if paper_account is None:
            return trade
        acct = await paper_account.get_account(trade.user_id)
        if not acct:
            return trade

        try:
            balance = float(acct.get("balance") or acct.get("starting_balance") or 0.0)
        except (TypeError, ValueError):
            return trade
        if balance <= 0:
            return trade

        expected_risk = balance * risk_pct / 100.0
        if expected_risk <= 0 or current_risk <= expected_risk * 1.05:
            return trade

        expected_reward = (
            expected_risk * trade.risk_reward_ratio
            if trade.risk_reward_ratio and trade.risk_reward_ratio > 0
            else trade.expected_reward
        )
        metadata = {
            **trade.metadata,
            "risk_amount_repaired": True,
            "original_risk_amount": current_risk,
            "repaired_risk_amount": expected_risk,
            "risk_repair_balance": balance,
            "risk_repair_reason": "paper_wallet_risk_percent",
        }
        await self._lifecycle_repo.update_trade(
            trade.id,
            TradeUpdateLifecycle(
                risk_amount=expected_risk,
                expected_reward=expected_reward,
                metadata=metadata,
            ),
        )
        await self._event_repo.create(TradeEventInsert(
            trade_id=trade.id,
            bot_id=trade.bot_id,
            user_id=trade.user_id,
            event_type="risk_amount_repaired",
            details={
                "old_risk_amount": current_risk,
                "new_risk_amount": expected_risk,
                "risk_percent": risk_pct,
                "balance": balance,
            },
        ))
        return trade.model_copy(update={
            "risk_amount": expected_risk,
            "expected_reward": expected_reward,
            "metadata": metadata,
        })

    async def _run_reconciliation(
        self,
        trade: Trade,
        exchange_account: Optional[ExchangeAccount],
    ) -> Optional[ReconciliationResult]:
        """
        Fetch real exchange order state and compare against DB state.

        SAFETY:
          - Paper/shadow are never reconciled here (caller gates on is_live).
          - On any exception or missing credentials → return None (fail-closed
            handled by caller).
          - NEVER closes a trade. Only auto-update allowed: partial fill qty.
        """
        if exchange_account is None:
            log.warning(
                "lifecycle.recon_no_exchange_account",
                trade_id=trade.id,
            )
            return None

        credentials: Optional[ApiCredentials] = None
        adapter: Optional[ExchangeAdapter]    = None

        try:
            credentials = await self._key_provider.get_credentials(exchange_account.id)
            adapter     = get_live_adapter(
                exchange=trade.exchange,
                api_key=credentials.api_key,
                api_secret=credentials.api_secret,
            )
            recon = await reconcile_trade(trade, adapter)
            log.info(
                "lifecycle.recon_complete",
                trade_id=trade.id,
                action=recon.action.action_type.name,
                exchange_status=recon.exchange_status,
                needs_update=recon.needs_update,
            )
            return recon

        except Exception as exc:
            log.error(
                "lifecycle.recon_exception",
                trade_id=trade.id,
                error=str(exc)[:300],
            )
            # Build a synthetic MARK_NEEDS_RECONCILIATION result so caller can
            # log + persist consistently rather than silently swallow.
            from src.lifecycle.action import LifecycleAction
            return ReconciliationResult(
                action=LifecycleAction(
                    action_type=ActionType.MARK_NEEDS_RECONCILIATION,
                    reason=f"Reconciliation error: {exc}",
                    metadata={
                        "trigger": "recon_exception",
                        "trade_id": trade.id,
                    },
                ),
            )
        finally:
            if credentials is not None:
                credentials.zero_out()
            if adapter is not None:
                try:
                    await adapter.close()
                except Exception:
                    pass

    async def _handle_reconciliation_result(
        self,
        *,
        trade: Trade,
        recon: ReconciliationResult,
        bot: Optional[Bot],
        exchange_account: Optional[ExchangeAccount],
        market_snapshot: Optional[MarketSnapshot],
        platform_settings: PlatformSettings,
        current_price: float,
    ) -> None:
        """
        Process a non-HOLD reconciliation result.

        Order:
          1. Apply allowed automatic update (filled_quantity for partial fill).
          2. Always write trade_event for visibility.
          3. Write security_log + audit_log for high-severity triggers.
          4. Apply the action via _apply_action (which routes mark_*).

        SAFETY: this method NEVER produces a CLOSE_* action — the
        ReconciliationService only emits HOLD / UPDATE_PNL / MARK_NEEDS_RECONCILIATION.
        """
        action  = recon.action
        trigger = action.metadata.get("trigger", "unknown")

        # ── 1. Allowed auto-update: partial-fill quantity only ─────────────────
        if recon.needs_update:
            log.info(
                "lifecycle.recon_trade_update",
                trade_id=trade.id,
                new_status=recon.new_status,
                new_filled_quantity=recon.new_filled_quantity,
            )
            await self._lifecycle_repo.update_trade(
                trade.id,
                TradeUpdateLifecycle(
                    status=recon.new_status,
                    filled_quantity=recon.new_filled_quantity,
                    avg_fill_price=recon.new_avg_fill_price,
                ),
            )

        # ── 2. Always write a trade_event for traceability ─────────────────────
        await self._event_repo.create(TradeEventInsert(
            trade_id=trade.id,
            bot_id=trade.bot_id,
            user_id=trade.user_id,
            event_type="reconciliation_anomaly"
                if action.action_type == ActionType.MARK_NEEDS_RECONCILIATION
                else "reconciliation_update",
            details={
                "trigger":         trigger,
                "exchange_status": recon.exchange_status,
                "action":          action.action_type.name,
                "reason":          action.reason,
                **action.metadata,
            },
        ))

        # ── 3. High-severity logging for known anomaly triggers ────────────────
        _CRITICAL_TRIGGERS = {
            "db_closed_exchange_open",       # CRITICAL — trade still open on exchange
            "db_open_exchange_filled",       # HIGH — exchange filled but DB open
            "unknown_exchange_status",       # HIGH — cannot interpret state
            "exchange_order_dead",           # HIGH — exchange cancelled/rejected
            "missing_order_id",              # HIGH — live trade with no order id
            "fetch_error",                   # HIGH — cannot reach exchange
            "recon_exception",               # HIGH — internal recon failure
        }

        if trigger in _CRITICAL_TRIGGERS:
            severity = (
                SeverityLevel.CRITICAL.value
                if trigger == "db_closed_exchange_open"
                else SeverityLevel.HIGH.value
            )

            await self._security_log.create(SecurityLogInsert(
                user_id=trade.user_id,
                event_type="reconciliation_anomaly",
                severity=severity,
                source="position_engine",
                message=f"Reconciliation anomaly ({trigger}): {action.reason[:280]}",
                metadata={
                    "trade_id":        trade.id,
                    "trigger":         trigger,
                    "exchange_status": recon.exchange_status,
                    "order_id":        trade.exchange_order_id,
                },
            ))

            await self._audit_log.create(AuditLogInsert(
                user_id=trade.user_id,
                action="reconciliation_anomaly",
                record_id=trade.id,
                table_name="trades",
                source="position_engine",
                metadata={
                    "trigger":         trigger,
                    "exchange_status": recon.exchange_status,
                    "reason":          action.reason[:300],
                },
            ))

            await self._risk_log.create(RiskLogInsert(
                user_id=trade.user_id,
                bot_id=trade.bot_id,
                trade_id=trade.id,
                risk_type="reconciliation_required",
                severity=severity,
                triggered=True,
                message=action.reason[:400],
                metadata={"trigger": trigger},
            ))

        # ── 4. Apply the action through the existing dispatch ──────────────────
        # NOTE: reconciliation can only emit HOLD / UPDATE_PNL /
        # MARK_NEEDS_RECONCILIATION. CLOSE_* paths are unreachable from here.
        await self._apply_action(
            trade=trade,
            action=action,
            current_price=current_price,
            bot=bot,
            exchange_account=exchange_account,
            market_snapshot=market_snapshot,
            platform_settings=platform_settings,
        )

    async def _apply_close(
        self,
        *,
        trade: Trade,
        action: LifecycleAction,
        current_price: float,
        exchange_account: Optional[ExchangeAccount],
        market_snapshot: Optional[MarketSnapshot],
        platform_settings: PlatformSettings,
        is_emergency: bool,
    ) -> None:
        """
        Apply a close action.

        For paper/shadow: simulate close, mark closed.
        For live: submit close order, confirm fill, mark closed.
        Unknown result → needs_reconciliation.
        """
        close_price = action.close_price or current_price
        event_type  = _action_to_event_type(action.action_type)
        risk_type   = _action_to_risk_type(action.action_type)

        # ── Risk guard before close ────────────────────────────────────────────
        risk_result = self._risk_guard.check_before_close(
            trade=trade,
            expected_close_price=close_price,
            market_snapshot=market_snapshot,
            platform_settings=platform_settings,
        )

        if risk_result.blocked:
            await self._risk_log.create(RiskLogInsert(
                user_id=trade.user_id,
                bot_id=trade.bot_id,
                trade_id=trade.id,
                risk_type="close_failed",
                severity=SeverityLevel.HIGH.value,
                triggered=True,
                message=f"Risk guard blocked close: {risk_result.reason[:300]}",
            ))
            await self._lifecycle_repo.release_claim(trade.id)
            return

        # ── Write trigger event ───────────────────────────────────────────────
        await self._event_repo.create(TradeEventInsert(
            trade_id=trade.id,
            bot_id=trade.bot_id,
            user_id=trade.user_id,
            event_type=event_type,
            details={
                "reason":      action.reason,
                "close_price": close_price,
                **action.metadata,
            },
        ))

        await self._risk_log.create(RiskLogInsert(
            user_id=trade.user_id,
            bot_id=trade.bot_id,
            trade_id=trade.id,
            risk_type=risk_type,
            severity=SeverityLevel.MEDIUM.value,
            triggered=True,
            message=action.reason[:400],
            metadata=action.metadata,
        ))

        # ── Execute close ─────────────────────────────────────────────────────
        if trade.mode in ("paper", "shadow"):
            await self._close_simulated(trade, close_price, action)
        else:
            # live
            await self._close_live(
                trade=trade,
                close_price=close_price,
                action=action,
                exchange_account=exchange_account,
                platform_settings=platform_settings,
                is_emergency=is_emergency,
            )

    # ── Simulated close (paper/shadow) ─────────────────────────────────────────

    async def _close_simulated(
        self, trade: Trade, close_price: float, action: LifecycleAction
    ) -> None:
        """Paper/shadow close — no exchange call, mark closed immediately."""
        if (
            action.metadata.get("scaled_take_profit")
            and not action.metadata.get("is_final_tp")
        ):
            await self._partial_close_simulated(trade, close_price, action)
            return

        close_realized_pnl = calculate_realized_pnl(trade, close_price)
        realized_pnl = float(trade.realized_pnl or 0.0) + close_realized_pnl
        pnl_pct      = pnl_percentage(realized_pnl, trade.effective_entry_price, _original_quantity(trade))
        r_multiple   = (
            realized_pnl / trade.risk_amount
            if trade.risk_amount and trade.risk_amount > 0
            else None
        )
        qty          = trade.effective_quantity

        log.info(
            "lifecycle.simulated_close",
            trade_id=trade.id,
            mode=trade.mode,
            close_price=close_price,
            realized_pnl=realized_pnl,
        )

        await self._lifecycle_repo.mark_closed(
            trade.id,
            exit_price=close_price,
            avg_exit_price=close_price,
            realized_pnl=realized_pnl,
            close_reason=_action_to_close_reason(action.action_type),
            pnl_pct=pnl_pct,
            r_multiple=r_multiple,
        )

        # Settle paper account ledger (paper-only). Best-effort — failures
        # here are logged but never block the close.
        if trade.mode == "paper":
            try:
                paper_account = getattr(self, "_paper_account", None) or PaperAccountService()
                reserved_on_open = trade.metadata.get("reserved_on_open", True)
                reserved_amount = self._paper_reserved_amount(trade) if reserved_on_open else 0.0
                await paper_account.settle_close(
                    user_id=trade.user_id,
                    trade_id=trade.id,
                    symbol=trade.symbol,
                    entry_price=trade.effective_entry_price,
                    exit_price=close_price,
                    quantity=qty,
                    direction=trade.direction,
                    realized_pnl=close_realized_pnl,
                    reserved_amount=reserved_amount,
                )
                await paper_account.sync_unrealized(user_id=trade.user_id)
            except Exception as exc:
                log.error(
                    "lifecycle.paper_account_settle_error",
                    trade_id=trade.id, error=str(exc)[:300],
                )

        await self._event_repo.create(TradeEventInsert(
            trade_id=trade.id,
            bot_id=trade.bot_id,
            user_id=trade.user_id,
            event_type="trade_closed",
            details={
                "mode":        trade.mode,
                "close_price": close_price,
                "realized_pnl": realized_pnl,
                "close_realized_pnl": close_realized_pnl,
                "pnl_pct":      pnl_pct,
                "r_multiple":   r_multiple,
                "close_reason": action.reason,
                "simulated":   True,
            },
        ))

        await self._audit_log.create(AuditLogInsert(
            user_id=trade.user_id,
            action="trade_closed",
            record_id=trade.id,
            table_name="trades",
            source="position_engine",
            metadata={
                "mode":        trade.mode,
                "close_price": close_price,
                "realized_pnl": realized_pnl,
                "close_realized_pnl": close_realized_pnl,
                "pnl_pct":      pnl_pct,
                "r_multiple":   r_multiple,
                "reason":      action.reason,
            },
        ))

        # Reload for notification
        fresh = await self._lifecycle_repo.get_by_id(trade.id)
        if fresh:
            await self._notifications.trade_closed(trade=fresh, reason=action.reason)

    # ── Live close ─────────────────────────────────────────────────────────────

    async def _partial_close_simulated(
        self, trade: Trade, close_price: float, action: LifecycleAction
    ) -> None:
        """Apply a paper/shadow scaled TP partial close and keep trade open."""
        qty = trade.effective_quantity
        close_qty = min(float(action.metadata.get("close_quantity") or 0.0), qty)
        if close_qty <= 0 or close_qty >= qty:
            action.metadata["is_final_tp"] = True
            await self._close_simulated(trade, close_price, action)
            return

        realized_pnl = _pnl_for_quantity(trade, close_price, close_qty)
        remaining_qty = max(0.0, qty - close_qty)
        level_no = int(action.metadata.get("tp_level") or 1)
        hit_at = utcnow_iso()
        old_plan = action.metadata.get("reward_plan") or trade.metadata.get("reward_plan") or {}
        new_plan = mark_level_hit(old_plan, level_no, qty=close_qty, pnl=realized_pnl, hit_at=hit_at)
        new_stop = next_stop_after_tp(trade, new_plan, level_no)
        next_take_profit = next_take_profit_after_tp(new_plan, level_no)
        cumulative_realized = float(trade.realized_pnl or 0.0) + realized_pnl
        original_qty = _original_quantity(trade)
        reserved_total = (
            self._paper_reserved_amount(trade) + float(trade.metadata.get("reserved_released") or 0.0)
            if trade.mode == "paper"
            else 0.0
        )
        reserved_release = (
            reserved_total * (close_qty / original_qty) if original_qty > 0 else 0.0
        )
        metadata = {
            **trade.metadata,
            "reward_plan": new_plan,
            "tp_plan": new_plan.get("levels", []),
            "scaled_tp_last_hit": level_no,
            "scaled_tp_realized_pnl": cumulative_realized,
            "reserved_released": (
                float(trade.metadata.get("reserved_released") or 0.0) + reserved_release
            ),
            "partial_close_history": [
                *(trade.metadata.get("partial_close_history") or []),
                {
                    "tp_level": level_no,
                    "price": close_price,
                    "quantity": close_qty,
                    "realized_pnl": realized_pnl,
                    "hit_at": hit_at,
                },
            ],
        }
        remaining_trade = trade.model_copy(update={"filled_quantity": remaining_qty})
        await self._lifecycle_repo.update_trade(
            trade.id,
            TradeUpdateLifecycle(
                lifecycle_status="idle",
                filled_quantity=remaining_qty,
                realized_pnl=cumulative_realized,
                unrealized_pnl=calculate_unrealized_pnl(remaining_trade, close_price),
                stop_loss=new_stop,
                take_profit=next_take_profit,
                metadata=metadata,
            ),
        )

        if trade.mode == "paper":
            try:
                paper_account = getattr(self, "_paper_account", None) or PaperAccountService()
                await paper_account.settle_close(
                    user_id=trade.user_id,
                    trade_id=trade.id,
                    symbol=trade.symbol,
                    entry_price=trade.effective_entry_price,
                    exit_price=close_price,
                    quantity=close_qty,
                    direction=trade.direction,
                    realized_pnl=realized_pnl,
                    reserved_amount=reserved_release,
                )
                await paper_account.sync_unrealized(user_id=trade.user_id)
            except Exception as exc:
                log.error(
                    "lifecycle.paper_account_partial_settle_error",
                    trade_id=trade.id,
                    error=str(exc)[:300],
                )

        await self._event_repo.create(TradeEventInsert(
            trade_id=trade.id,
            bot_id=trade.bot_id,
            user_id=trade.user_id,
            event_type="take_profit_partial_closed",
            details={
                "tp_level": level_no,
                "close_price": close_price,
                "closed_quantity": close_qty,
                "remaining_quantity": remaining_qty,
                "realized_pnl": realized_pnl,
                "cumulative_realized_pnl": cumulative_realized,
                "new_stop_loss": new_stop,
                "next_take_profit": next_take_profit,
                "reward_plan": new_plan,
                "reason": action.reason,
            },
        ))

        await self._risk_log.create(RiskLogInsert(
            user_id=trade.user_id,
            bot_id=trade.bot_id,
            trade_id=trade.id,
            risk_type="take_profit_partial_closed",
            severity=SeverityLevel.INFO.value,
            triggered=True,
            message=action.reason[:400],
            metadata={"tp_level": level_no, "remaining_quantity": remaining_qty},
        ))

        await self._lifecycle_repo.release_claim(trade.id)

    async def _close_live(
        self,
        *,
        trade: Trade,
        close_price: float,
        action: LifecycleAction,
        exchange_account: Optional[ExchangeAccount],
        platform_settings: PlatformSettings,
        is_emergency: bool,
    ) -> None:
        """
        Submit a live close order with full confirmation.

        Flow:
          1. Security guard for live close (checks gates + exchange account)
          2. Load API credentials
          3. check_permissions() — block if can_withdraw=True
          4. Mark lifecycle_status='closing' with close_order_id placeholder
          5. place_order() with deterministic client_order_id
          6. fetch_order() — confirm fill
          7. mark_closed() or needs_reconciliation

        NEVER blindly retry on unknown result.
        """
        # ── Security guard for live close ──────────────────────────────────────
        sec_result = self._security_guard.check(
            trade=trade,
            bot=None,  # already checked in pipeline
            user_settings=None,
            exchange_account=exchange_account,
            platform_settings=platform_settings,
            critical_security_event_count=0,
            is_emergency_close=is_emergency,
        )

        if sec_result.blocked:
            # Check if emergency close is disabled — pause instead of failing
            ec_blocked = any(
                c.name == "emergency_close_gate" and not c.passed
                for c in sec_result.checks
            )
            if ec_blocked:
                log.warning(
                    "lifecycle.emergency_close_disabled",
                    trade_id=trade.id,
                    reason=sec_result.reason[:200],
                )
                await self._security_log.create(SecurityLogInsert(
                    user_id=trade.user_id,
                    event_type="live_close_blocked",
                    severity=SeverityLevel.HIGH.value,
                    source="position_engine",
                    message=(
                        "Emergency close disabled in platform_settings. "
                        "Pausing monitoring instead of closing."
                    ),
                    metadata={"trade_id": trade.id},
                ))
                await self._lifecycle_repo.release_claim(trade.id)
                return

            await self._security_log.create(SecurityLogInsert(
                user_id=trade.user_id,
                event_type="live_close_blocked",
                severity=SeverityLevel.CRITICAL.value,
                source="position_engine",
                message=f"Security guard blocked live close: {sec_result.reason[:300]}",
                metadata={"trade_id": trade.id},
            ))
            await self._lifecycle_repo.release_claim(trade.id)
            return

        if exchange_account is None:
            await self._lifecycle_repo.mark_needs_reconciliation(
                trade.id, "No exchange account for live close"
            )
            return

        # ── Load credentials ──────────────────────────────────────────────────
        credentials: Optional[ApiCredentials] = None
        adapter: Optional[ExchangeAdapter]    = None

        close_quantity = min(
            float(action.metadata.get("close_quantity") or trade.effective_quantity),
            trade.effective_quantity,
        )
        close_side     = "sell" if trade.is_long else "buy"
        client_order_id = self._make_close_client_order_id(trade)

        try:
            credentials = await self._key_provider.get_credentials(exchange_account.id)
            adapter     = get_live_adapter(
                exchange=trade.exchange,
                api_key=credentials.api_key,
                api_secret=credentials.api_secret,
            )

            # Defence-in-depth permission check
            perm = await adapter.check_permissions()
            if not perm.safe:
                raise RuntimeError(
                    f"API key unsafe: can_trade={perm.can_trade}, "
                    f"can_withdraw={perm.can_withdraw}"
                )

            # Mark lifecycle as 'closing' before submitting order
            await self._lifecycle_repo.update_trade(
                trade.id,
                TradeUpdateLifecycle(
                    lifecycle_status="closing",
                    close_order_id=f"pending-{client_order_id}",
                ),
            )

            log.info(
                "lifecycle.submitting_close_order",
                trade_id=trade.id,
                side=close_side,
                quantity=close_quantity,
                # DO NOT log api_key
            )

            await self._event_repo.create(TradeEventInsert(
                trade_id=trade.id,
                bot_id=trade.bot_id,
                user_id=trade.user_id,
                event_type="close_order_submitted",
                details={
                    "side":           close_side,
                    "quantity":       close_quantity,
                    "client_order_id": client_order_id,
                    "reason":         action.reason,
                },
            ))

            order_req = OrderRequest(
                exchange=trade.exchange,
                symbol=trade.symbol,
                side=close_side,
                order_type="market",
                quantity=close_quantity,
                client_order_id=client_order_id,
                metadata={"trade_id": trade.id, "close_reason": action.reason},
            )

            result = await adapter.place_order(order_req)

        except Exception as exc:
            log.error(
                "lifecycle.close_order_exception",
                trade_id=trade.id,
                error=str(exc)[:300],
            )
            await self._security_log.create(SecurityLogInsert(
                user_id=trade.user_id,
                event_type="exchange_order_unknown",
                severity=SeverityLevel.CRITICAL.value,
                source="position_engine",
                message=f"Close order exception: {exc}",
                metadata={"trade_id": trade.id},
            ))
            await self._lifecycle_repo.mark_needs_reconciliation(
                trade.id, f"Close order exception: {exc}"
            )
            return
        finally:
            if credentials is not None:
                credentials.zero_out()
            if adapter is not None:
                try:
                    await adapter.close()
                except Exception:
                    pass

        # ── Confirm fill ──────────────────────────────────────────────────────
        await self._confirm_live_close(trade, result, close_price, action, exchange_account)

    async def _confirm_live_close(
        self,
        trade: Trade,
        place_result: OrderResult,
        expected_price: float,
        action: LifecycleAction,
        exchange_account: ExchangeAccount,
    ) -> None:
        """
        After place_order, fetch the order to confirm fill status.

        filled   → mark trade closed
        partial  → mark closed with actual filled_quantity + partial_fill flag
        unknown  → needs_reconciliation (NEVER blind retry)
        rejected → needs_reconciliation
        """
        if not place_result.success or not place_result.order_id:
            err = place_result.error or "no order_id returned"
            await self._event_repo.create(TradeEventInsert(
                trade_id=trade.id,
                bot_id=trade.bot_id,
                user_id=trade.user_id,
                event_type="close_order_failed",
                details={"error": err},
            ))
            await self._lifecycle_repo.mark_needs_reconciliation(
                trade.id, f"Close order failed: {err}"
            )
            return

        # Fetch confirmation from exchange
        credentials: Optional[ApiCredentials] = None
        adapter: Optional[ExchangeAdapter]    = None
        try:
            credentials = await self._key_provider.get_credentials(exchange_account.id)
            adapter     = get_live_adapter(
                exchange=trade.exchange,
                api_key=credentials.api_key,
                api_secret=credentials.api_secret,
            )
            confirmed = await adapter.fetch_order(place_result.order_id, trade.symbol)
        except Exception as exc:
            log.error(
                "lifecycle.fetch_close_order_failed",
                trade_id=trade.id,
                order_id=place_result.order_id,
                error=str(exc)[:200],
            )
            await self._lifecycle_repo.mark_needs_reconciliation(
                trade.id, f"Cannot confirm close order: {exc}"
            )
            return
        finally:
            if credentials is not None:
                credentials.zero_out()
            if adapter is not None:
                try:
                    await adapter.close()
                except Exception:
                    pass

        exchange_status = (confirmed.status or "unknown").lower()

        # ── Filled → mark closed ──────────────────────────────────────────────
        if exchange_status in _CLOSE_FILLED_STATUSES:
            fill_price   = confirmed.avg_fill_price or expected_price
            filled_qty   = confirmed.filled_quantity or trade.effective_quantity
            if (
                action.metadata.get("scaled_take_profit")
                and not action.metadata.get("is_final_tp")
            ):
                action.metadata["close_quantity"] = filled_qty
                await self._partial_close_simulated(trade, fill_price, action)
                return
            close_realized_pnl = calculate_realized_pnl(trade, fill_price)
            realized_pnl = float(trade.realized_pnl or 0.0) + close_realized_pnl
            pnl_pct      = pnl_percentage(realized_pnl, trade.effective_entry_price, _original_quantity(trade))
            r_multiple   = (
                realized_pnl / trade.risk_amount
                if trade.risk_amount and trade.risk_amount > 0
                else None
            )

            await self._event_repo.create(TradeEventInsert(
                trade_id=trade.id,
                bot_id=trade.bot_id,
                user_id=trade.user_id,
                event_type="close_order_confirmed",
                details={
                    "exchange_status":  exchange_status,
                    "fill_price":       fill_price,
                    "filled_qty":       filled_qty,
                    "order_id":         place_result.order_id,
                },
            ))

            await self._lifecycle_repo.mark_closed(
                trade.id,
                exit_price=fill_price,
                avg_exit_price=fill_price,
                realized_pnl=realized_pnl,
                close_reason=_action_to_close_reason(action.action_type),
                close_order_id=place_result.order_id,
                pnl_pct=pnl_pct,
                r_multiple=r_multiple,
            )

            await self._audit_log.create(AuditLogInsert(
                user_id=trade.user_id,
                action="trade_closed",
                record_id=trade.id,
                table_name="trades",
                source="position_engine",
                metadata={
                    "mode":        trade.mode,
                    "close_price": fill_price,
                    "realized_pnl": realized_pnl,
                    "close_realized_pnl": close_realized_pnl,
                    "pnl_pct":      pnl_pct,
                    "r_multiple":   r_multiple,
                    "order_id":    place_result.order_id,
                },
            ))

            fresh = await self._lifecycle_repo.get_by_id(trade.id)
            if fresh:
                await self._notifications.trade_closed(trade=fresh, reason=action.reason)

        # ── Partial fill → close with actual quantity ──────────────────────────
        elif exchange_status in _CLOSE_PARTIAL_STATUSES:
            fill_price  = confirmed.avg_fill_price or expected_price
            filled_qty  = confirmed.filled_quantity or 0.0
            close_realized_pnl = calculate_realized_pnl(trade, fill_price)
            realized_pnl = float(trade.realized_pnl or 0.0) + close_realized_pnl
            pnl_pct      = pnl_percentage(realized_pnl, trade.effective_entry_price, _original_quantity(trade))
            r_multiple   = (
                realized_pnl / trade.risk_amount
                if trade.risk_amount and trade.risk_amount > 0
                else None
            )

            log.warning(
                "lifecycle.partial_close_fill",
                trade_id=trade.id,
                filled_qty=filled_qty,
                expected_qty=trade.effective_quantity,
            )

            await self._risk_log.create(RiskLogInsert(
                user_id=trade.user_id,
                bot_id=trade.bot_id,
                trade_id=trade.id,
                risk_type="slippage_exceeded",
                severity=SeverityLevel.HIGH.value,
                triggered=True,
                message=f"Partial close fill: {filled_qty} of {trade.effective_quantity}",
                metadata={"filled_qty": filled_qty, "expected": trade.effective_quantity},
            ))

            await self._lifecycle_repo.mark_closed(
                trade.id,
                exit_price=fill_price,
                avg_exit_price=fill_price,
                realized_pnl=realized_pnl,
                close_reason=_action_to_close_reason(action.action_type),
                close_order_id=place_result.order_id,
                pnl_pct=pnl_pct,
                r_multiple=r_multiple,
            )

            await self._event_repo.create(TradeEventInsert(
                trade_id=trade.id,
                bot_id=trade.bot_id,
                user_id=trade.user_id,
                event_type="close_order_confirmed",
                details={
                    "exchange_status": exchange_status,
                    "filled_qty":      filled_qty,
                    "partial_fill":    True,
                    "fill_price":      fill_price,
                },
            ))

        # ── Unknown / rejected → needs_reconciliation ─────────────────────────
        else:
            await self._security_log.create(SecurityLogInsert(
                user_id=trade.user_id,
                event_type="exchange_order_unknown",
                severity=SeverityLevel.CRITICAL.value,
                source="position_engine",
                message=(
                    f"Close order returned unknown status '{exchange_status}'. "
                    "Manual reconciliation required."
                ),
                metadata={
                    "trade_id":        trade.id,
                    "order_id":        place_result.order_id,
                    "exchange_status": exchange_status,
                },
            ))

            await self._event_repo.create(TradeEventInsert(
                trade_id=trade.id,
                bot_id=trade.bot_id,
                user_id=trade.user_id,
                event_type="close_order_failed",
                details={
                    "exchange_status": exchange_status,
                    "order_id":        place_result.order_id,
                    "note":            "Unknown/rejected — needs_reconciliation",
                },
            ))

            await self._lifecycle_repo.mark_needs_reconciliation(
                trade.id,
                f"Close order status unknown: '{exchange_status}' — do not retry blindly",
            )
            await self._notifications.reconciliation_required(
                trade=trade, reason=f"Close order status '{exchange_status}' unknown"
            )

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _make_close_client_order_id(trade: Trade) -> str:
        """Deterministic idempotency key for close orders."""
        raw = f"close:{trade.id}:{trade.exchange}:{trade.symbol}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    @staticmethod
    def _paper_reserved_amount(trade: Trade) -> float:
        """Return the cash reserved when this paper trade opened.

        Newer paper trades persist metadata.reserved_amount. Older rows did not,
        so fall back to notional/effective entry * quantity to release the full
        reserved balance on close.
        """
        candidates = (
            trade.metadata.get("reserved_amount"),
            trade.metadata.get("notional"),
            trade.notional,
            trade.effective_entry_price * trade.effective_quantity,
        )
        for value in candidates:
            try:
                amount = float(value or 0.0)
            except (TypeError, ValueError):
                continue
            if amount > 0:
                released = float(trade.metadata.get("reserved_released") or 0.0)
                return max(0.0, amount - released)
        return 0.0

    async def _fail(self, trade: Trade, error: str) -> None:
        """Mark lifecycle as failed — last resort error handler."""
        try:
            await self._lifecycle_repo.mark_failed(trade.id, error)
            await self._audit_log.create(AuditLogInsert(
                user_id=trade.user_id,
                action="lifecycle_failed",
                record_id=trade.id,
                table_name="trades",
                source="position_engine",
                metadata={"error": error[:300]},
            ))
        except Exception as exc:
            log.error(
                "lifecycle.mark_failed_error",
                trade_id=trade.id,
                original_error=error[:100],
                meta_error=str(exc)[:100],
            )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _action_to_event_type(atype: ActionType) -> str:
    return {
        ActionType.CLOSE_STOP_LOSS:     "stop_loss_triggered",
        ActionType.CLOSE_TAKE_PROFIT:   "take_profit_triggered",
        ActionType.CLOSE_TRAILING_STOP: "trailing_stop_triggered",
        ActionType.CLOSE_EMERGENCY:     "emergency_close_triggered",
    }.get(atype, "lifecycle_error")


def _action_to_risk_type(atype: ActionType) -> str:
    return {
        ActionType.CLOSE_STOP_LOSS:     "stop_loss_triggered",
        ActionType.CLOSE_TAKE_PROFIT:   "take_profit_triggered",
        ActionType.CLOSE_TRAILING_STOP: "trailing_stop_triggered",
        ActionType.CLOSE_EMERGENCY:     "max_drawdown_close",
    }.get(atype, "close_failed")


def _action_to_close_reason(atype: ActionType) -> str:
    return {
        ActionType.CLOSE_STOP_LOSS:     "stop_loss",
        ActionType.CLOSE_TAKE_PROFIT:   "take_profit",
        ActionType.CLOSE_TRAILING_STOP: "trailing_stop",
        ActionType.CLOSE_EMERGENCY:     "emergency",
    }.get(atype, "manual")


def _pnl_for_quantity(trade: Trade, exit_price: float, quantity: float) -> float:
    entry = trade.effective_entry_price
    if quantity <= 0 or entry <= 0 or exit_price <= 0:
        return 0.0
    if trade.is_long:
        return (exit_price - entry) * quantity
    return (entry - exit_price) * quantity


def _original_quantity(trade: Trade) -> float:
    for value in (
        trade.metadata.get("initial_quantity"),
        trade.metadata.get("original_quantity"),
        trade.quantity,
        trade.effective_quantity,
    ):
        try:
            qty = float(value or 0.0)
        except (TypeError, ValueError):
            continue
        if qty > 0:
            return qty
    return 0.0
