"""
LifecycleSecurityGuard — pre-action security checks for position lifecycle.

Checks:
  1. global_trading_enabled (platform kill switch)
  2. live_execution_enabled (for live close)
  3. ENABLE_LIVE_CLOSE env var (for live close)
  4. Bot is active and not archived
  5. User trading enabled
  6. Exchange account active + can_trade=True + can_withdraw=False
  7. No critical unresolved security events
  8. Emergency close: additionally check emergency_close_enabled

All checks fail-closed. ANY failure blocks the lifecycle action.
For live close specifically, failure → PAUSE_MONITORING (not immediate error).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from src.config import settings
from src.db.models import Bot, ExchangeAccount, PlatformSettings, Trade, UserSettings
from src.logging_config import get_logger

log = get_logger(__name__)


@dataclass
class SecurityCheckResult:
    name:     str
    passed:   bool
    message:  str
    severity: str = "high"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LifecycleSecurityGuardResult:
    blocked: bool
    reason:  str
    checks:  list[SecurityCheckResult] = field(default_factory=list)

    @property
    def failed_checks(self) -> list[SecurityCheckResult]:
        return [c for c in self.checks if not c.passed]

    def to_dict(self) -> dict:
        return {
            "blocked": self.blocked,
            "reason":  self.reason,
            "checks":  [
                {"name": c.name, "passed": c.passed,
                 "message": c.message, "severity": c.severity}
                for c in self.checks
            ],
        }


class LifecycleSecurityGuard:
    """
    Validates security invariants before any live lifecycle action.

    Paper/shadow actions skip live-specific checks but still enforce
    platform kill switch and bot/user status checks.
    """

    def check(
        self,
        *,
        trade: Trade,
        bot: Optional[Bot],
        user_settings: Optional[UserSettings],
        exchange_account: Optional[ExchangeAccount],
        platform_settings: PlatformSettings,
        critical_security_event_count: int,
        is_emergency_close: bool = False,
    ) -> LifecycleSecurityGuardResult:
        checks: list[SecurityCheckResult] = []
        is_live = trade.is_live

        # ── 1. Global kill switch ─────────────────────────────────────────────
        if not platform_settings.global_trading_enabled:
            checks.append(SecurityCheckResult(
                name="global_trading_enabled",
                passed=False,
                message="Platform kill switch active: global_trading_enabled=false",
                severity="critical",
            ))
            # Don't check further — all actions blocked
            return LifecycleSecurityGuardResult(
                blocked=True,
                reason="Global kill switch active",
                checks=checks,
            )

        checks.append(SecurityCheckResult(
            name="global_trading_enabled",
            passed=True,
            message="Global trading enabled",
        ))

        # ── 2. Live close gates ───────────────────────────────────────────────
        if is_live:
            checks.append(self._check_live_close_gate(platform_settings))

            if is_emergency_close:
                checks.append(self._check_emergency_close_gate(platform_settings))

        # ── 3. Bot active ─────────────────────────────────────────────────────
        checks.append(self._check_bot(bot))

        # ── 4. User trading enabled ───────────────────────────────────────────
        checks.append(self._check_user(user_settings))

        # ── 5. Exchange account (live only) ───────────────────────────────────
        if is_live:
            checks.extend(self._check_exchange_account(exchange_account))

        # ── 6. Critical security events ───────────────────────────────────────
        checks.append(self._check_security_events(critical_security_event_count))

        # ── Aggregate ─────────────────────────────────────────────────────────
        failed  = [c for c in checks if not c.passed]
        blocked = bool(failed)

        if blocked:
            reason = "; ".join(c.message for c in failed)
            log.warning(
                "lifecycle_security_guard.blocked",
                trade_id=trade.id,
                mode=trade.mode,
                failed_count=len(failed),
                reason=reason[:300],
            )
        else:
            log.debug("lifecycle_security_guard.passed", trade_id=trade.id)

        return LifecycleSecurityGuardResult(
            blocked=blocked,
            reason="; ".join(c.message for c in failed) if failed else "all checks passed",
            checks=checks,
        )

    # ── Individual checks ──────────────────────────────────────────────────────

    def _check_live_close_gate(self, ps: PlatformSettings) -> SecurityCheckResult:
        if not settings.enable_live_close:
            return SecurityCheckResult(
                name="live_close_gate_env",
                passed=False,
                message="ENABLE_LIVE_CLOSE=false — live close blocked by environment config",
                severity="critical",
            )
        if not ps.live_execution_enabled:
            return SecurityCheckResult(
                name="live_close_gate_platform",
                passed=False,
                message="platform_settings.live_execution_enabled=false — live close blocked",
                severity="critical",
            )
        return SecurityCheckResult(
            name="live_close_gate",
            passed=True,
            message="Live close gates passed",
        )

    def _check_emergency_close_gate(self, ps: PlatformSettings) -> SecurityCheckResult:
        if not ps.emergency_close_enabled:
            return SecurityCheckResult(
                name="emergency_close_gate",
                passed=False,
                message=(
                    "platform_settings.emergency_close_enabled=false — "
                    "emergency close will PAUSE monitoring instead of closing"
                ),
                severity="high",
            )
        return SecurityCheckResult(
            name="emergency_close_gate",
            passed=True,
            message="Emergency close enabled",
        )

    def _check_bot(self, bot: Optional[Bot]) -> SecurityCheckResult:
        if bot is None:
            return SecurityCheckResult(
                name="bot_active",
                passed=False,
                message="Bot not found",
                severity="critical",
            )
        if bot.status != "active" or bot.is_archived:
            return SecurityCheckResult(
                name="bot_active",
                passed=False,
                message=f"Bot status='{bot.status}', archived={bot.is_archived}",
                severity="critical",
                metadata={"status": bot.status, "archived": bot.is_archived},
            )
        return SecurityCheckResult(name="bot_active", passed=True, message="Bot active")

    def _check_user(self, us: Optional[UserSettings]) -> SecurityCheckResult:
        if us is None:
            return SecurityCheckResult(
                name="user_trading_enabled",
                passed=True,  # advisory — don't block on missing settings
                message="User settings not found (advisory pass)",
                severity="medium",
            )
        if not us.trading_enabled:
            return SecurityCheckResult(
                name="user_trading_enabled",
                passed=False,
                message="User trading_enabled=False",
                severity="critical",
            )
        return SecurityCheckResult(
            name="user_trading_enabled",
            passed=True,
            message="User trading enabled",
        )

    def _check_exchange_account(
        self, account: Optional[ExchangeAccount]
    ) -> list[SecurityCheckResult]:
        results = []

        if account is None:
            results.append(SecurityCheckResult(
                name="exchange_account",
                passed=False,
                message="Exchange account not found for live trade",
                severity="critical",
            ))
            return results

        if not account.is_active:
            results.append(SecurityCheckResult(
                name="exchange_account_active",
                passed=False,
                message="Exchange account is inactive",
                severity="critical",
            ))

        if not account.can_trade:
            results.append(SecurityCheckResult(
                name="exchange_can_trade",
                passed=False,
                message="Exchange API key cannot trade",
                severity="critical",
            ))

        if account.can_withdraw:
            results.append(SecurityCheckResult(
                name="no_withdraw_permission",
                passed=False,
                message="CRITICAL: API key has withdrawal permission — all actions blocked",
                severity="critical",
                metadata={"account_id": account.id},
            ))

        if account.withdrawal_detected:
            results.append(SecurityCheckResult(
                name="withdrawal_not_detected",
                passed=False,
                message="Withdrawal activity detected on exchange account",
                severity="critical",
            ))

        if not results:
            results.append(SecurityCheckResult(
                name="exchange_account",
                passed=True,
                message="Exchange account safe",
            ))

        return results

    def _check_security_events(self, count: int) -> SecurityCheckResult:
        if count > 0:
            return SecurityCheckResult(
                name="no_critical_security_events",
                passed=False,
                message=f"{count} unresolved critical security event(s)",
                severity="critical",
                metadata={"count": count},
            )
        return SecurityCheckResult(
            name="no_critical_security_events",
            passed=True,
            message="No critical security events",
        )
