"""
Emergency close / pause evaluation.

Checks (in order):
  1. global_trading_enabled = False  → CLOSE_EMERGENCY (or PAUSE if live close disabled)
  2. Critical unresolved security events for user → PAUSE_MONITORING
  3. Bot status is not 'active'       → PAUSE_MONITORING
  4. Exchange account unsafe (live)   → CLOSE_EMERGENCY / PAUSE_MONITORING
  5. User banned / trading disabled   → PAUSE_MONITORING

Returns CLOSE_EMERGENCY or PAUSE_MONITORING if any condition met; HOLD otherwise.
"""
from __future__ import annotations

from typing import Optional

from src.db.models import Bot, ExchangeAccount, PlatformSettings, Trade, UserSettings
from src.lifecycle.action import ActionType, LifecycleAction, hold


def check_emergency(
    *,
    trade: Trade,
    bot: Optional[Bot],
    user_settings: Optional[UserSettings],
    exchange_account: Optional[ExchangeAccount],
    platform_settings: PlatformSettings,
    critical_security_event_count: int,
    current_price: float,
) -> LifecycleAction:
    """
    Evaluate all emergency conditions for a trade.

    Returns CLOSE_EMERGENCY if immediate closure is warranted,
    PAUSE_MONITORING if monitoring should stop without closing,
    or HOLD if no emergency condition.
    """
    # ── 1. Global kill switch ─────────────────────────────────────────────────
    if not platform_settings.global_trading_enabled:
        return LifecycleAction(
            action_type=ActionType.CLOSE_EMERGENCY,
            reason="Global kill switch active: global_trading_enabled=false",
            close_price=current_price,
            metadata={"trigger": "global_kill_switch"},
        )

    # ── 2. Critical unresolved security events ────────────────────────────────
    if critical_security_event_count > 0:
        return LifecycleAction(
            action_type=ActionType.PAUSE_MONITORING,
            reason=(
                f"{critical_security_event_count} unresolved critical security event(s). "
                "Pausing lifecycle monitoring until resolved."
            ),
            metadata={
                "trigger": "critical_security_events",
                "count": critical_security_event_count,
            },
        )

    # ── 3. Bot not active ─────────────────────────────────────────────────────
    if bot is None:
        return LifecycleAction(
            action_type=ActionType.PAUSE_MONITORING,
            reason="Bot not found in database — pausing lifecycle monitoring",
            metadata={"trigger": "bot_not_found"},
        )

    if bot.status not in ("active",):
        return LifecycleAction(
            action_type=ActionType.PAUSE_MONITORING,
            reason=f"Bot status is '{bot.status}' (expected 'active') — pausing monitoring",
            metadata={"trigger": "bot_not_active", "bot_status": bot.status},
        )

    if bot.is_archived:
        return LifecycleAction(
            action_type=ActionType.PAUSE_MONITORING,
            reason="Bot is archived — pausing lifecycle monitoring",
            metadata={"trigger": "bot_archived"},
        )

    # ── 4. User banned / trading disabled ─────────────────────────────────────
    if user_settings is not None and not user_settings.trading_enabled:
        return LifecycleAction(
            action_type=ActionType.PAUSE_MONITORING,
            reason="User trading_enabled=False — pausing lifecycle monitoring",
            metadata={"trigger": "user_trading_disabled"},
        )

    # ── 5. Exchange account unsafe (live trades only) ─────────────────────────
    if trade.is_live:
        ea_result = _check_exchange_account(exchange_account, current_price)
        if ea_result is not None:
            return ea_result

    return hold()


def _check_exchange_account(
    account: Optional[ExchangeAccount],
    current_price: float,
) -> Optional[LifecycleAction]:
    if account is None:
        return LifecycleAction(
            action_type=ActionType.PAUSE_MONITORING,
            reason="Exchange account not found for live trade — pausing monitoring",
            metadata={"trigger": "exchange_account_not_found"},
        )

    if not account.is_active:
        return LifecycleAction(
            action_type=ActionType.PAUSE_MONITORING,
            reason="Exchange account is inactive — pausing monitoring",
            metadata={"trigger": "exchange_account_inactive"},
        )

    if account.can_withdraw:
        return LifecycleAction(
            action_type=ActionType.CLOSE_EMERGENCY,
            reason=(
                "CRITICAL: Exchange API key has withdrawal permission. "
                "Emergency close triggered."
            ),
            close_price=current_price,
            metadata={
                "trigger":    "withdrawal_permission_detected",
                "account_id": account.id,
            },
        )

    if account.withdrawal_detected:
        return LifecycleAction(
            action_type=ActionType.CLOSE_EMERGENCY,
            reason=(
                "Withdrawal activity detected on exchange account. "
                "Emergency close triggered."
            ),
            close_price=current_price,
            metadata={
                "trigger":    "withdrawal_detected",
                "account_id": account.id,
            },
        )

    if not account.can_trade:
        return LifecycleAction(
            action_type=ActionType.PAUSE_MONITORING,
            reason="Exchange API key lost trade permission — pausing monitoring",
            metadata={"trigger": "trade_permission_lost"},
        )

    return None
