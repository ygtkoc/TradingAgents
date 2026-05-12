"""
Tests for SecurityExecutionGuard.

ANY failed check must block execution (fail-closed).
"""
from __future__ import annotations

import pytest

from src.guards.security_guard import SecurityExecutionGuard
from tests.conftest import (
    make_bot,
    make_decision,
    make_exchange_account,
    make_user_settings,
    minutes_ago_str,
)


_MISSING = object()


def _run(
    decision=_MISSING,
    bot=_MISSING,
    user_settings=_MISSING,
    exchange_account=_MISSING,
    critical_security_event_count=0,
):
    guard = SecurityExecutionGuard()
    return guard.check(
        decision=decision if decision is not _MISSING else make_decision(),
        bot=bot if bot is not _MISSING else make_bot(),
        user_settings=user_settings if user_settings is not _MISSING else make_user_settings(),
        exchange_account=exchange_account if exchange_account is not _MISSING else make_exchange_account(),
        critical_security_event_count=critical_security_event_count,
    )


class TestBotActive:
    def test_active_bot_passes(self):
        bot = make_bot(status="active")
        result = _run(bot=bot)
        check = next(c for c in result.checks if c.name == "bot_active")
        assert check.passed

    def test_paused_bot_blocks(self):
        bot = make_bot(status="paused")
        result = _run(bot=bot)
        check = next(c for c in result.checks if c.name == "bot_active")
        assert not check.passed
        assert result.blocked

    def test_no_bot_blocks(self):
        result = _run(bot=None)
        check = next(c for c in result.checks if c.name == "bot_active")
        assert not check.passed
        assert result.blocked

    def test_archived_bot_blocks(self):
        bot = make_bot(status="active", is_archived=True)
        result = _run(bot=bot)
        check = next(c for c in result.checks if c.name == "bot_active")
        assert not check.passed
        assert result.blocked


class TestUserLivePermission:
    def test_paper_mode_skips_user_permission_check(self):
        # Paper mode doesn't include user_live_permission check
        decision = make_decision(mode="paper")
        result = _run(decision=decision)
        names = [c.name for c in result.checks]
        assert "user_live_permission" not in names

    def test_live_mode_checks_user_permission(self):
        decision = make_decision(mode="live")
        us = make_user_settings(
            trading_enabled=True,
            real_trading_enabled=True,
            real_trading_allowed=True,
        )
        result = _run(decision=decision, user_settings=us)
        names = [c.name for c in result.checks]
        assert "user_live_permission" in names

    def test_trading_disabled_blocks_live(self):
        decision = make_decision(mode="live")
        us = make_user_settings(trading_enabled=False)
        result = _run(decision=decision, user_settings=us)
        check = next(c for c in result.checks if c.name == "user_live_permission")
        assert not check.passed
        assert result.blocked

    def test_real_trading_not_allowed_blocks(self):
        decision = make_decision(mode="live")
        us = make_user_settings(
            trading_enabled=True,
            real_trading_enabled=True,
            real_trading_allowed=False,
        )
        result = _run(decision=decision, user_settings=us)
        check = next(c for c in result.checks if c.name == "user_live_permission")
        assert not check.passed


class TestWithdrawPermission:
    def test_no_withdraw_permission_passes(self):
        account = make_exchange_account(can_withdraw=False)
        result = _run(exchange_account=account)
        check = next(c for c in result.checks if c.name == "no_withdraw_permission")
        assert check.passed

    def test_withdraw_permission_blocks_unconditionally(self):
        """Critical: can_withdraw=True must ALWAYS block regardless of other state."""
        account = make_exchange_account(can_withdraw=True)
        result = _run(exchange_account=account)
        check = next(c for c in result.checks if c.name == "no_withdraw_permission")
        assert not check.passed
        assert result.blocked

    def test_withdrawal_detected_blocks(self):
        account = make_exchange_account(can_withdraw=False, withdrawal_detected=True)
        result = _run(exchange_account=account)
        check = next(c for c in result.checks if c.name == "withdrawal_not_detected")
        assert not check.passed
        assert result.blocked


class TestExchangeAccount:
    def test_no_account_blocks(self):
        result = _run(exchange_account=None)
        check = next(c for c in result.checks if c.name == "exchange_account_exists")
        assert not check.passed
        assert result.blocked

    def test_inactive_account_blocks(self):
        account = make_exchange_account(is_active=False)
        result = _run(exchange_account=account)
        check = next(c for c in result.checks if c.name == "exchange_account_active")
        assert not check.passed
        assert result.blocked

    def test_cannot_trade_blocks(self):
        account = make_exchange_account(can_trade=False)
        result = _run(exchange_account=account)
        check = next(c for c in result.checks if c.name == "can_trade")
        assert not check.passed
        assert result.blocked


class TestCriticalSecurityEvents:
    def test_no_events_passes(self):
        result = _run(critical_security_event_count=0)
        check = next(c for c in result.checks if c.name == "no_critical_security_events")
        assert check.passed

    def test_one_critical_event_blocks(self):
        result = _run(critical_security_event_count=1)
        check = next(c for c in result.checks if c.name == "no_critical_security_events")
        assert not check.passed
        assert result.blocked


class TestDecisionStaleness:
    def test_fresh_decision_passes(self):
        decision = make_decision(created_at=minutes_ago_str(5))
        result = _run(decision=decision)
        check = next(c for c in result.checks if c.name == "decision_not_stale")
        assert check.passed

    def test_stale_decision_blocks(self):
        decision = make_decision(created_at=minutes_ago_str(120))
        result = _run(decision=decision)
        check = next(c for c in result.checks if c.name == "decision_not_stale")
        assert not check.passed
        assert result.blocked


class TestAgentRunId:
    def test_with_agent_run_id_passes(self):
        decision = make_decision(agent_run_id="run-abc")
        result = _run(decision=decision)
        check = next(c for c in result.checks if c.name == "agent_run_id_present")
        assert check.passed

    def test_no_agent_run_id_blocks(self):
        decision = make_decision(agent_run_id=None)
        result = _run(decision=decision)
        check = next(c for c in result.checks if c.name == "agent_run_id_present")
        assert not check.passed
        assert result.blocked


class TestInjectionDetection:
    def test_no_injection_passes(self):
        decision = make_decision(security_summary={"injection_detected": False})
        result = _run(decision=decision)
        check = next(c for c in result.checks if c.name == "no_injection_detected")
        assert check.passed

    def test_injection_detected_blocks(self):
        decision = make_decision(security_summary={"injection_detected": True})
        result = _run(decision=decision)
        check = next(c for c in result.checks if c.name == "no_injection_detected")
        assert not check.passed
        assert result.blocked

    def test_empty_security_summary_passes(self):
        decision = make_decision(security_summary={})
        result = _run(decision=decision)
        check = next(c for c in result.checks if c.name == "no_injection_detected")
        assert check.passed


class TestVetoSummary:
    def test_no_veto_passes(self):
        decision = make_decision(veto_summary={"vetoed": False})
        result = _run(decision=decision)
        check = next(c for c in result.checks if c.name == "veto_summary_clear")
        assert check.passed

    def test_vetoed_blocks(self):
        decision = make_decision(
            veto_summary={
                "vetoed": True,
                "resolved_decision": "pause_trading",
                "veto_reason": "injection detected",
            }
        )
        result = _run(decision=decision)
        check = next(c for c in result.checks if c.name == "veto_summary_clear")
        assert not check.passed
        assert result.blocked

    def test_empty_veto_summary_passes(self):
        decision = make_decision(veto_summary={})
        result = _run(decision=decision)
        check = next(c for c in result.checks if c.name == "veto_summary_clear")
        assert check.passed


class TestActionableDecision:
    @pytest.mark.parametrize("fd", ["open_long", "open_short"])
    def test_actionable_decisions_pass(self, fd):
        decision = make_decision(final_decision=fd)
        result = _run(decision=decision)
        check = next(c for c in result.checks if c.name == "actionable_decision")
        assert check.passed

    @pytest.mark.parametrize("fd", ["wait", "reject", "pause_trading", "manual_approval_required"])
    def test_non_actionable_decisions_block(self, fd):
        decision = make_decision(final_decision=fd)
        result = _run(decision=decision)
        check = next(c for c in result.checks if c.name == "actionable_decision")
        assert not check.passed
        assert result.blocked


class TestApprovalStatus:
    @pytest.mark.parametrize("status", ["approved", "auto_approved"])
    def test_valid_approval_statuses_pass(self, status):
        decision = make_decision(approval_status=status)
        result = _run(decision=decision)
        check = next(c for c in result.checks if c.name == "approval_status_valid")
        assert check.passed

    @pytest.mark.parametrize("status", ["pending", "rejected", "manual_review", ""])
    def test_invalid_approval_statuses_block(self, status):
        decision = make_decision(approval_status=status)
        result = _run(decision=decision)
        check = next(c for c in result.checks if c.name == "approval_status_valid")
        assert not check.passed
        assert result.blocked


class TestAllPassed:
    def test_clean_paper_decision_passes_all(self):
        result = _run()
        assert not result.blocked
        assert result.reason == "all security checks passed"

    def test_result_to_dict(self):
        result = _run()
        d = result.to_dict()
        assert "blocked" in d
        assert "checks" in d
        assert isinstance(d["checks"], list)
