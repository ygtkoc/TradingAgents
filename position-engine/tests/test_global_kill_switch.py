"""
Tests for global kill switch behaviour across all lifecycle modules.

The global kill switch (platform_settings.global_trading_enabled=False) must:
  1. emergency.py: immediately return CLOSE_EMERGENCY regardless of other state
  2. lifecycle_security_guard.py: immediately block (return blocked=True, abort all checks)
  3. Both short-circuit — no other checks are evaluated after the kill switch fires

Additional kill switch tests:
  - live_execution_enabled=False blocks live close gate
  - emergency_close_enabled=False pauses instead of closing
"""
import pytest

from src.lifecycle.action import ActionType
from src.lifecycle.emergency import check_emergency
from src.guards.lifecycle_security_guard import LifecycleSecurityGuard
from tests.conftest import (
    make_trade,
    make_bot,
    make_user_settings,
    make_exchange_account,
    make_platform_settings,
)


# ── emergency.py kill switch ───────────────────────────────────────────────────

class TestKillSwitchEmergency:
    """check_emergency() must return CLOSE_EMERGENCY when global kill switch fires."""

    def _check(self, **ps_kwargs):
        trade    = make_trade(mode="live", direction="long")
        bot      = make_bot(status="active")
        us       = make_user_settings(trading_enabled=True)
        ea       = make_exchange_account(can_withdraw=False, can_trade=True)
        ps       = make_platform_settings(**ps_kwargs)
        return check_emergency(
            trade=trade,
            bot=bot,
            user_settings=us,
            exchange_account=ea,
            platform_settings=ps,
            critical_security_event_count=0,
            current_price=50_000.0,
        )

    def test_kill_switch_triggers_emergency_close(self):
        action = self._check(global_trading_enabled=False)
        assert action.action_type == ActionType.CLOSE_EMERGENCY

    def test_kill_switch_reason_mentions_kill_switch(self):
        action = self._check(global_trading_enabled=False)
        assert "kill switch" in action.reason.lower() or "global" in action.reason.lower()

    def test_kill_switch_metadata_trigger(self):
        action = self._check(global_trading_enabled=False)
        assert action.metadata.get("trigger") == "global_kill_switch"

    def test_kill_switch_has_close_price(self):
        action = self._check(global_trading_enabled=False)
        assert action.close_price == pytest.approx(50_000.0)

    def test_kill_switch_takes_priority_over_everything(self):
        """Even if bot is None and security events exist, kill switch wins."""
        trade = make_trade(mode="live", direction="long")
        ps    = make_platform_settings(global_trading_enabled=False)
        action = check_emergency(
            trade=trade,
            bot=None,  # would normally cause PAUSE
            user_settings=None,
            exchange_account=None,
            platform_settings=ps,
            critical_security_event_count=5,  # would cause PAUSE
            current_price=50_000.0,
        )
        assert action.action_type == ActionType.CLOSE_EMERGENCY

    def test_enabled_returns_hold_for_healthy_state(self):
        action = self._check(global_trading_enabled=True)
        assert action.action_type == ActionType.HOLD


# ── lifecycle_security_guard.py kill switch ────────────────────────────────────

class TestKillSwitchSecurityGuard:
    """LifecycleSecurityGuard.check() must block immediately on global kill switch."""

    def _guard(self) -> LifecycleSecurityGuard:
        return LifecycleSecurityGuard()

    def _check(self, ps_kwargs=None, mode="paper", **extra):
        """Use paper mode by default so the live-close gate does not interfere."""
        ps_kwargs = ps_kwargs or {}
        guard = self._guard()
        trade = make_trade(mode=mode, direction="long")
        bot   = make_bot(status="active")
        us    = make_user_settings()
        ea    = make_exchange_account(can_withdraw=False, can_trade=True)
        ps    = make_platform_settings(**ps_kwargs)
        return guard.check(
            trade=trade,
            bot=bot,
            user_settings=us,
            exchange_account=ea,
            platform_settings=ps,
            critical_security_event_count=0,
            **extra,
        )

    def test_kill_switch_blocks_execution(self):
        result = self._check(ps_kwargs={"global_trading_enabled": False})
        assert result.blocked is True

    def test_kill_switch_reason_mentions_global(self):
        result = self._check(ps_kwargs={"global_trading_enabled": False})
        assert "global" in result.reason.lower() or "kill switch" in result.reason.lower()

    def test_kill_switch_short_circuits_other_checks(self):
        """After kill switch fires, no further checks should be in results."""
        result = self._check(ps_kwargs={"global_trading_enabled": False})
        # Only the kill switch check should be present (short-circuit)
        assert len(result.checks) == 1
        assert result.checks[0].name == "global_trading_enabled"
        assert result.checks[0].passed is False

    def test_enabled_does_not_block_for_kill_switch(self):
        """With global_trading_enabled=True, the kill switch check itself passes."""
        result = self._check(ps_kwargs={"global_trading_enabled": True})
        ks_check = next((c for c in result.checks if c.name == "global_trading_enabled"), None)
        assert ks_check is not None
        assert ks_check.passed is True


# ── live_execution_enabled gate ────────────────────────────────────────────────

class TestLiveExecutionGate:
    """live_execution_enabled=False must block live close gate."""

    def _guard_check(self, live_enabled=False):
        guard = LifecycleSecurityGuard()
        trade = make_trade(mode="live", direction="long")
        ps = make_platform_settings(
            global_trading_enabled=True,
            live_execution_enabled=live_enabled,
        )
        return guard.check(
            trade=trade,
            bot=make_bot(status="active"),
            user_settings=make_user_settings(),
            exchange_account=make_exchange_account(can_withdraw=False),
            platform_settings=ps,
            critical_security_event_count=0,
        )

    def test_live_execution_disabled_blocks(self):
        result = self._guard_check(live_enabled=False)
        assert result.blocked is True
        gate_checks = [c for c in result.checks if "live_close_gate" in c.name]
        assert len(gate_checks) >= 1
        assert any(not c.passed for c in gate_checks)

    def test_live_execution_enabled_passes_gate(self):
        from unittest.mock import patch
        with patch("src.guards.lifecycle_security_guard.settings") as mock_settings:
            mock_settings.enable_live_close = True
            result = self._guard_check(live_enabled=True)
        # The gate check itself should pass now
        gate_checks = [c for c in result.checks if "live_close_gate" in c.name]
        assert all(c.passed for c in gate_checks)


# ── emergency_close_enabled gate ──────────────────────────────────────────────

class TestEmergencyCloseGate:
    """When emergency_close_enabled=False and is_emergency_close=True, guard flags the gate check."""

    def test_emergency_close_disabled_flags_gate_check(self):
        from unittest.mock import patch
        guard = LifecycleSecurityGuard()
        trade = make_trade(mode="live", direction="long")
        ps = make_platform_settings(
            global_trading_enabled=True,
            live_execution_enabled=True,
            emergency_close_enabled=False,
        )
        with patch("src.guards.lifecycle_security_guard.settings") as mock_settings:
            mock_settings.enable_live_close = True
            result = guard.check(
                trade=trade,
                bot=make_bot(status="active"),
                user_settings=make_user_settings(),
                exchange_account=make_exchange_account(can_withdraw=False),
                platform_settings=ps,
                critical_security_event_count=0,
                is_emergency_close=True,
            )
        # The emergency_close_gate check should be present and failed
        ec_checks = [c for c in result.checks if c.name == "emergency_close_gate"]
        assert len(ec_checks) == 1
        assert ec_checks[0].passed is False

    def test_emergency_close_enabled_passes_gate(self):
        from unittest.mock import patch
        guard = LifecycleSecurityGuard()
        trade = make_trade(mode="live", direction="long")
        ps = make_platform_settings(
            global_trading_enabled=True,
            live_execution_enabled=True,
            emergency_close_enabled=True,
        )
        with patch("src.guards.lifecycle_security_guard.settings") as mock_settings:
            mock_settings.enable_live_close = True
            result = guard.check(
                trade=trade,
                bot=make_bot(status="active"),
                user_settings=make_user_settings(),
                exchange_account=make_exchange_account(can_withdraw=False),
                platform_settings=ps,
                critical_security_event_count=0,
                is_emergency_close=True,
            )
        ec_checks = [c for c in result.checks if c.name == "emergency_close_gate"]
        assert all(c.passed for c in ec_checks)
