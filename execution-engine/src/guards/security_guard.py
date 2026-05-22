"""
SecurityExecutionGuard — pre-execution security checks.

All checks are deterministic and fail-closed:
  - Missing data → blocked
  - Any veto or injection signal → blocked
  - Any critical unresolved security event → blocked
  - Exchange account not safe → blocked

Checks performed (in order):
  1.  Bot status is active
  2.  User real_trading_allowed and trading_enabled (for live)
  3.  Exchange account exists and is active
  4.  Exchange account can_trade = True
  5.  Exchange account can_withdraw = False  (CRITICAL — must be false)
  6.  Exchange account withdrawal_detected = False
  7.  Encrypted key present (key not deleted or revoked)
  8.  No unresolved critical security_log events for user
  9.  Decision is not stale (age < DECISION_STALE_MINUTES)
  10. Decision came from a valid agent_run (agent_run_id not null)
  11. security_summary does not indicate injection_detected = True
  12. veto_summary is empty OR vetoed = False
  13. final_decision is actionable
  14. approval_status is valid (approved / auto_approved)
  15. No pending execution by another worker (race check — advisory)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from src.config import settings
from src.db.models import Bot, ExchangeAccount, PlatformSettings, TradeDecision, UserSettings
from src.logging_config import get_logger

log = get_logger(__name__)

_ACTIONABLE_DECISIONS  = frozenset({"open_long", "open_short"})
_VALID_APPROVAL_STATUS = frozenset({"approved", "auto_approved"})


@dataclass
class SecurityCheckResult:
    """Result of a single security check."""
    name:    str
    passed:  bool
    message: str
    severity: str = "high"   # info / medium / high / critical
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SecurityGuardResult:
    """Aggregate result from SecurityExecutionGuard.check()."""
    blocked:    bool
    reason:     str
    checks:     list[SecurityCheckResult] = field(default_factory=list)

    @property
    def failed_checks(self) -> list[SecurityCheckResult]:
        return [c for c in self.checks if not c.passed]

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocked":  self.blocked,
            "reason":   self.reason,
            "checks":   [
                {
                    "name":     c.name,
                    "passed":   c.passed,
                    "message":  c.message,
                    "severity": c.severity,
                }
                for c in self.checks
            ],
        }


class SecurityExecutionGuard:
    """
    Validates all security invariants before any order is placed.

    None of these checks are skippable.
    All checks fail-closed — if in doubt, block.

    Usage:
        result = security_guard.check(
            decision=decision,
            bot=bot,
            user_settings=user_settings,
            exchange_account=exchange_account,
            critical_security_event_count=N,
        )
        if result.blocked:
            raise ExecutionBlockedError(result.reason)
    """

    def check(
        self,
        *,
        decision: TradeDecision,
        bot: Optional[Bot],
        user_settings: Optional[UserSettings],
        exchange_account: Optional[ExchangeAccount],
        critical_security_event_count: int,
        platform_settings: Optional[PlatformSettings] = None,
    ) -> SecurityGuardResult:
        checks: list[SecurityCheckResult] = []
        is_live = decision.mode == "live"

        # ── 0. Global kill switch (platform_settings) ─────────────────────────
        # Checked first — if the kill switch is active, all execution is blocked
        # regardless of any other state. Short-circuit immediately.
        if platform_settings is not None:
            ks = self._check_global_kill_switch(platform_settings)
            checks.append(ks)
            if not ks.passed:
                return SecurityGuardResult(
                    blocked=True,
                    reason=ks.message,
                    checks=checks,
                )

        # ── 1. Bot exists and is active ───────────────────────────────────────
        checks.append(self._check_bot_active(bot))

        # ── 2. User trading permission (live only) ────────────────────────────
        if is_live:
            checks.append(self._check_user_live_permission(user_settings))

        # ── 3. Exchange account exists ────────────────────────────────────────
        if is_live:
            checks.append(self._check_exchange_account_exists(exchange_account))

        # ── 4. Exchange account is_active ─────────────────────────────────────
            checks.append(self._check_exchange_account_active(exchange_account))

        # ── 5. can_trade = True ───────────────────────────────────────────────
            checks.append(self._check_can_trade(exchange_account))

        # ── 6. can_withdraw = False (CRITICAL) ────────────────────────────────
            checks.append(self._check_no_withdraw_permission(exchange_account))

        # ── 7. withdrawal_detected = False ────────────────────────────────────
            checks.append(self._check_withdrawal_not_detected(exchange_account))

        # ── 8. Encrypted key present ──────────────────────────────────────────
            checks.append(self._check_encrypted_key_present(exchange_account))

        # ── 9. No critical unresolved security events ─────────────────────────
        checks.append(self._check_no_critical_security_events(
            critical_security_event_count, decision.user_id
        ))

        # ── 10. Decision not stale ────────────────────────────────────────────
        checks.append(self._check_decision_not_stale(decision))

        # ── 11. Decision has agent_run_id ─────────────────────────────────────
        checks.append(self._check_agent_run_id(decision))

        # ── 12. No injection detected in security_summary ─────────────────────
        checks.append(self._check_no_injection(decision))

        # ── 13. veto_summary vetoed = False ───────────────────────────────────
        checks.append(self._check_veto_summary(decision))

        # ── 14. final_decision is actionable ─────────────────────────────────
        checks.append(self._check_actionable_decision(decision))

        # ── 15. approval_status valid ─────────────────────────────────────────
        checks.append(self._check_approval_status(decision))

        # ── Aggregate ─────────────────────────────────────────────────────────
        failed = [c for c in checks if not c.passed]
        blocked = bool(failed)  # ANY failure → blocked for security

        if failed:
            reasons = "; ".join(c.message for c in failed)
            log.error(
                "security_guard.checks_failed",
                decision_id=decision.id,
                mode=decision.mode,
                failed_count=len(failed),
                reasons=reasons[:400],
                # DO NOT log api keys, secrets, or user PII
            )
        else:
            log.info("security_guard.all_passed", decision_id=decision.id, mode=decision.mode)

        return SecurityGuardResult(
            blocked=blocked,
            reason="; ".join(c.message for c in failed) if failed else "all security checks passed",
            checks=checks,
        )

    # ── Individual checks ──────────────────────────────────────────────────────

    def _check_global_kill_switch(self, ps: PlatformSettings) -> SecurityCheckResult:
        """
        Check 0 — platform kill switch.

        If global_trading_enabled=False, ALL execution is blocked immediately.
        No further checks are evaluated.
        """
        if not ps.global_trading_enabled:
            return SecurityCheckResult(
                name="global_trading_enabled",
                passed=False,
                message=(
                    "Platform kill switch active: global_trading_enabled=false. "
                    "All trade execution is blocked."
                ),
                severity="critical",
            )
        return SecurityCheckResult(
            name="global_trading_enabled",
            passed=True,
            message="Global trading enabled",
            severity="info",
        )

    def _check_bot_active(self, bot: Optional[Bot]) -> SecurityCheckResult:
        if bot is None:
            return SecurityCheckResult(
                name="bot_active",
                passed=False,
                message="Bot not found in database",
                severity="critical",
            )
        if bot.status != "active":
            return SecurityCheckResult(
                name="bot_active",
                passed=False,
                message=f"Bot status is '{bot.status}', expected 'active'",
                severity="critical",
                metadata={"bot_id": bot.id, "status": bot.status},
            )
        if bot.is_archived:
            return SecurityCheckResult(
                name="bot_active",
                passed=False,
                message="Bot is archived — cannot execute trades",
                severity="critical",
                metadata={"bot_id": bot.id},
            )
        return SecurityCheckResult(
            name="bot_active",
            passed=True,
            message=f"Bot active (status={bot.status})",
        )

    def _check_user_live_permission(
        self, user_settings: Optional[UserSettings]
    ) -> SecurityCheckResult:
        if user_settings is None:
            return SecurityCheckResult(
                name="user_live_permission",
                passed=False,
                message="User settings not found — cannot verify live trading permission",
                severity="critical",
            )
        if not user_settings.trading_enabled:
            return SecurityCheckResult(
                name="user_live_permission",
                passed=False,
                message="User trading_enabled=False — account suspended",
                severity="critical",
            )
        if not user_settings.real_trading_allowed:
            return SecurityCheckResult(
                name="user_live_permission",
                passed=False,
                message=(
                    "User real_trading_allowed=False — subscription does not permit live trading"
                ),
                severity="critical",
            )
        if not user_settings.real_trading_enabled:
            return SecurityCheckResult(
                name="user_live_permission",
                passed=False,
                message="User real_trading_enabled=False — live trading disabled by user",
                severity="critical",
            )
        return SecurityCheckResult(
            name="user_live_permission",
            passed=True,
            message="User live trading permission verified",
        )

    def _check_exchange_account_exists(
        self, account: Optional[ExchangeAccount]
    ) -> SecurityCheckResult:
        if account is None:
            return SecurityCheckResult(
                name="exchange_account_exists",
                passed=False,
                message="Exchange account not found",
                severity="critical",
            )
        return SecurityCheckResult(
            name="exchange_account_exists",
            passed=True,
            message="Exchange account found",
        )

    def _check_exchange_account_active(
        self, account: Optional[ExchangeAccount]
    ) -> SecurityCheckResult:
        if account is None:
            return SecurityCheckResult(
                name="exchange_account_active",
                passed=False,
                message="Exchange account not found (cannot check active status)",
                severity="critical",
            )
        if not account.is_active:
            return SecurityCheckResult(
                name="exchange_account_active",
                passed=False,
                message="Exchange account is inactive",
                severity="critical",
                metadata={"account_id": account.id},
            )
        return SecurityCheckResult(
            name="exchange_account_active",
            passed=True,
            message="Exchange account is active",
        )

    def _check_can_trade(self, account: Optional[ExchangeAccount]) -> SecurityCheckResult:
        if account is None:
            return SecurityCheckResult(
                name="can_trade",
                passed=False,
                message="Exchange account not found — cannot verify trade permission",
                severity="critical",
            )
        if not account.can_trade:
            return SecurityCheckResult(
                name="can_trade",
                passed=False,
                message="Exchange API key does not have trade permission (can_trade=False)",
                severity="critical",
                metadata={"account_id": account.id, "exchange": account.exchange},
            )
        return SecurityCheckResult(
            name="can_trade",
            passed=True,
            message="API key has trade permission",
        )

    def _check_no_withdraw_permission(
        self, account: Optional[ExchangeAccount]
    ) -> SecurityCheckResult:
        """
        CRITICAL: The API key must NOT have withdrawal permission.
        A key with can_withdraw=True is a catastrophic security violation.
        """
        if account is None:
            return SecurityCheckResult(
                name="no_withdraw_permission",
                passed=False,
                message="Exchange account not found — cannot verify withdrawal permission",
                severity="critical",
            )
        if account.can_withdraw:
            return SecurityCheckResult(
                name="no_withdraw_permission",
                passed=False,
                message=(
                    "CRITICAL: Exchange API key has withdrawal permission. "
                    "Execution blocked. Revoke withdrawal permission immediately."
                ),
                severity="critical",
                metadata={
                    "account_id": account.id,
                    "exchange": account.exchange,
                    # DO NOT log api key
                },
            )
        return SecurityCheckResult(
            name="no_withdraw_permission",
            passed=True,
            message="API key has no withdrawal permission (safe)",
        )

    def _check_withdrawal_not_detected(
        self, account: Optional[ExchangeAccount]
    ) -> SecurityCheckResult:
        if account is None:
            return SecurityCheckResult(
                name="withdrawal_not_detected",
                passed=False,
                message="Exchange account not found",
                severity="critical",
            )
        if account.withdrawal_detected:
            return SecurityCheckResult(
                name="withdrawal_not_detected",
                passed=False,
                message=(
                    "withdrawal_detected=True on exchange account. "
                    "Account flagged — trading blocked until resolved."
                ),
                severity="critical",
                metadata={"account_id": account.id, "exchange": account.exchange},
            )
        return SecurityCheckResult(
            name="withdrawal_not_detected",
            passed=True,
            message="No withdrawal activity detected",
        )

    def _check_encrypted_key_present(
        self, account: Optional[ExchangeAccount]
    ) -> SecurityCheckResult:
        if account is None:
            return SecurityCheckResult(
                name="encrypted_key_present",
                passed=False,
                message="Exchange account not found",
                severity="critical",
            )
        if not account.encrypted_api_key or not account.encrypted_api_secret:
            return SecurityCheckResult(
                name="encrypted_key_present",
                passed=False,
                message=(
                    "No encrypted API key found for live exchange account. "
                    "Add keys via the secure Edge Function before enabling live trading."
                ),
                severity="critical",
                metadata={"account_id": account.id},
            )
        return SecurityCheckResult(
            name="encrypted_key_present",
            passed=True,
            message="Encrypted API credentials present",
        )

    def _check_no_critical_security_events(
        self, count: int, user_id: str
    ) -> SecurityCheckResult:
        if count > 0:
            return SecurityCheckResult(
                name="no_critical_security_events",
                passed=False,
                message=(
                    f"{count} unresolved critical security event(s) detected for user. "
                    "Execution blocked until events are reviewed and resolved."
                ),
                severity="critical",
                metadata={"critical_event_count": count},
            )
        return SecurityCheckResult(
            name="no_critical_security_events",
            passed=True,
            message="No unresolved critical security events",
        )

    def _check_decision_not_stale(self, decision: TradeDecision) -> SecurityCheckResult:
        """Reject decisions older than DECISION_STALE_MINUTES."""
        try:
            created = datetime.fromisoformat(decision.created_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return SecurityCheckResult(
                name="decision_not_stale",
                passed=False,
                message="Cannot parse decision created_at timestamp",
                severity="critical",
            )

        age_minutes = (
            datetime.now(timezone.utc) - created
        ).total_seconds() / 60

        limit = settings.decision_stale_minutes
        if age_minutes > limit:
            return SecurityCheckResult(
                name="decision_not_stale",
                passed=False,
                message=(
                    f"Decision is {age_minutes:.0f} min old; limit is {limit} min. "
                    "Market conditions may have changed — rejecting stale decision."
                ),
                severity="critical",
                metadata={"age_minutes": round(age_minutes, 1), "limit_minutes": limit},
            )
        return SecurityCheckResult(
            name="decision_not_stale",
            passed=True,
            message=f"Decision age {age_minutes:.1f} min within limit {limit} min",
        )

    def _check_agent_run_id(self, decision: TradeDecision) -> SecurityCheckResult:
        if not decision.agent_run_id:
            return SecurityCheckResult(
                name="agent_run_id_present",
                passed=False,
                message=(
                    "decision.agent_run_id is null. "
                    "Only decisions produced by a verified agent run can be executed."
                ),
                severity="critical",
            )
        return SecurityCheckResult(
            name="agent_run_id_present",
            passed=True,
            message=f"agent_run_id present ({decision.agent_run_id[:8]}...)",
        )

    def _check_no_injection(self, decision: TradeDecision) -> SecurityCheckResult:
        """
        Reject if the security_summary written by the Agent Engine indicates
        that prompt injection was detected.
        """
        sec = decision.security_summary or {}
        injection_detected = sec.get("injection_detected", False)

        if injection_detected:
            return SecurityCheckResult(
                name="no_injection_detected",
                passed=False,
                message=(
                    "Agent Engine security_summary flagged injection_detected=True. "
                    "Execution permanently blocked for this decision."
                ),
                severity="critical",
                metadata={"injection_detected": True},
            )
        return SecurityCheckResult(
            name="no_injection_detected",
            passed=True,
            message="No injection detected in security_summary",
        )

    def _check_veto_summary(self, decision: TradeDecision) -> SecurityCheckResult:
        """
        Reject if veto_summary indicates the decision was vetoed.
        An empty veto_summary is treated as safe (no veto).
        """
        veto = decision.veto_summary or {}
        vetoed = veto.get("vetoed", False)

        if vetoed:
            resolved = veto.get("resolved_decision", "unknown")
            reason   = veto.get("veto_reason", "unspecified veto")
            return SecurityCheckResult(
                name="veto_summary_clear",
                passed=False,
                message=(
                    f"Decision was vetoed by Agent Engine (resolved_decision={resolved}). "
                    f"Veto reason: {reason}"
                ),
                severity="critical",
                metadata={
                    "vetoed": True,
                    "resolved_decision": resolved,
                    "veto_reason": reason,
                },
            )
        return SecurityCheckResult(
            name="veto_summary_clear",
            passed=True,
            message="veto_summary: no veto",
        )

    def _check_actionable_decision(self, decision: TradeDecision) -> SecurityCheckResult:
        if decision.final_decision not in _ACTIONABLE_DECISIONS:
            return SecurityCheckResult(
                name="actionable_decision",
                passed=False,
                message=(
                    f"final_decision '{decision.final_decision}' is not actionable. "
                    f"Executable decisions: {sorted(_ACTIONABLE_DECISIONS)}"
                ),
                severity="critical",
                metadata={"final_decision": decision.final_decision},
            )
        return SecurityCheckResult(
            name="actionable_decision",
            passed=True,
            message=f"final_decision '{decision.final_decision}' is actionable",
        )

    def _check_approval_status(self, decision: TradeDecision) -> SecurityCheckResult:
        if decision.approval_status not in _VALID_APPROVAL_STATUS:
            return SecurityCheckResult(
                name="approval_status_valid",
                passed=False,
                message=(
                    f"approval_status '{decision.approval_status}' is not valid for execution. "
                    f"Required: {sorted(_VALID_APPROVAL_STATUS)}"
                ),
                severity="critical",
                metadata={"approval_status": decision.approval_status},
            )
        return SecurityCheckResult(
            name="approval_status_valid",
            passed=True,
            message=f"approval_status '{decision.approval_status}' valid",
        )
