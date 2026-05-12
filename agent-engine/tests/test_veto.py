"""
Tests for the veto detection, severity classification, and summary building utilities.

Security patch coverage:
  FIX 4: build_veto_summary() returns VetoSummaryResult dataclass (never None).
         Use veto_summary_to_dict() to get the serialisable form.
         Veto severity determines the resolved_decision:
           security injection  → pause_trading
           risk critical       → reject
           bot policy limits   → wait
"""
from __future__ import annotations

import pytest

from src.db.models import AgentDecision
from src.orchestration.veto import (
    VetoClassification,
    VetoSummaryResult,
    build_veto_summary,
    check_for_veto,
    classify_veto,
    collect_all_flags,
    derive_severity_from_flags,
    veto_summary_to_dict,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _result(
    name: str,
    category: str = "risk",
    veto: bool = False,
    risk_flags=None,
    security_flags=None,
    reasoning: str = "",
) -> dict:
    return {
        "agent_name": name,
        "agent_category": category,
        "veto": veto,
        "score": -100.0 if veto else 50.0,
        "confidence": 1.0,
        "reasoning": reasoning or f"{name} reasoning",
        "risk_flags": risk_flags or [],
        "security_flags": security_flags or [],
    }


# ── check_for_veto ─────────────────────────────────────────────────────────────

def test_no_veto_returns_false():
    results = [_result("agent_a"), _result("agent_b")]
    triggered, name = check_for_veto(results)
    assert triggered is False
    assert name is None


def test_single_veto_detected():
    results = [
        _result("agent_a"),
        _result("risk_auditor", veto=True),
        _result("agent_c"),
    ]
    triggered, name = check_for_veto(results)
    assert triggered is True
    assert name == "risk_auditor"


def test_first_veto_wins():
    """When multiple agents veto, the first one in the list wins."""
    results = [
        _result("agent_a", veto=True),
        _result("agent_b", veto=True),
    ]
    triggered, name = check_for_veto(results)
    assert name == "agent_a"


def test_empty_results_no_veto():
    triggered, name = check_for_veto([])
    assert triggered is False
    assert name is None


# ── build_veto_summary — returns VetoSummaryResult dataclass ──────────────────

def test_build_veto_summary_no_veto_returns_vetoed_false():
    """
    FIX 4: build_veto_summary never returns None.
    When no veto is present, it returns VetoSummaryResult(vetoed=False).
    """
    results = [_result("agent_a"), _result("agent_b")]
    summary = build_veto_summary(results)
    assert isinstance(summary, VetoSummaryResult)
    assert summary.vetoed is False
    assert summary.primary is None
    assert summary.all_vetoes == []


def test_build_veto_summary_includes_veto_details():
    """
    FIX 4: veto_summary_to_dict() provides the serialisable form.
    Use it to get the dict representation for DB storage.
    """
    results = [
        _result(
            "security_guardian",
            category="security",
            veto=True,
            security_flags=["metadata_injection_attempt"],
        )
    ]
    summary = build_veto_summary(results)
    assert isinstance(summary, VetoSummaryResult)
    assert summary.vetoed is True
    assert summary.primary is not None
    assert summary.primary.agent_name == "security_guardian"
    assert "metadata_injection_attempt" in summary.all_security_flags

    # Dict form via veto_summary_to_dict()
    d = veto_summary_to_dict(summary)
    assert d["vetoed"] is True
    assert d["primary_agent"] == "security_guardian"
    assert "metadata_injection_attempt" in d["all_security_flags"]


def test_build_veto_summary_truncates_reasoning():
    """Reasoning stored in VetoClassification is capped at 500 chars."""
    long_reason = "x" * 1000
    results = [
        {
            "agent_name": "test",
            "agent_category": "security",
            "veto": True,
            "score": -100.0,
            "confidence": 1.0,
            "reasoning": long_reason,
            "risk_flags": [],
            "security_flags": [],
        }
    ]
    summary = build_veto_summary(results)
    assert len(summary.primary.reasoning) <= 500

    d = veto_summary_to_dict(summary)
    assert len(d["primary_reasoning"]) <= 500


def test_build_veto_summary_collects_all_vetoing_agents():
    """
    FIX 4: build_veto_summary collects ALL vetoing agents, not just the first.
    all_vetoes must include every agent that set veto=True.
    """
    results = [
        _result("risk_auditor", veto=True, risk_flags=["extreme_spread"]),
        _result(
            "security_guardian", category="security", veto=True,
            security_flags=["metadata_injection_attempt"],
        ),
        _result("clean_agent", veto=False),
    ]
    summary = build_veto_summary(results)
    assert summary.vetoed is True
    assert len(summary.all_vetoes) == 2
    agent_names = {vc.agent_name for vc in summary.all_vetoes}
    assert "risk_auditor" in agent_names
    assert "security_guardian" in agent_names


# ── FIX 4: Severity-mapped resolved_decision tests ────────────────────────────

def test_security_injection_resolves_to_pause_trading():
    """
    FIX 4: Injection flags in a security veto must resolve to pause_trading,
    not the generic 'reject'. This is a critical safety property.
    """
    results = [
        _result(
            "prompt_injection_defense",
            category="security",
            veto=True,
            security_flags=["metadata_injection_attempt"],
        )
    ]
    summary = build_veto_summary(results)
    assert summary.resolved_decision == AgentDecision.PAUSE_TRADING.value


def test_agent_reasoning_injection_resolves_to_pause_trading():
    results = [
        _result(
            "security_guardian",
            category="security",
            veto=True,
            security_flags=["agent_reasoning_injection"],
        )
    ]
    summary = build_veto_summary(results)
    assert summary.resolved_decision == AgentDecision.PAUSE_TRADING.value


def test_extreme_spread_resolves_to_reject():
    """High-severity risk flags resolve to reject."""
    results = [
        _result("risk_auditor", veto=True, risk_flags=["extreme_spread"])
    ]
    summary = build_veto_summary(results)
    assert summary.resolved_decision == AgentDecision.REJECT.value


def test_position_limit_resolves_to_wait():
    """Policy-level risk flags resolve to wait, not reject."""
    results = [
        _result("chief_risk_officer", veto=True, risk_flags=["position_limit_reached"])
    ]
    summary = build_veto_summary(results)
    assert summary.resolved_decision == AgentDecision.WAIT.value


def test_bot_not_active_resolves_to_wait():
    results = [
        _result("chief_risk_officer", veto=True, risk_flags=["bot_not_active"])
    ]
    summary = build_veto_summary(results)
    assert summary.resolved_decision == AgentDecision.WAIT.value


def test_highest_severity_veto_wins():
    """
    FIX 4: When multiple vetoes fire, the highest-severity one determines
    the resolved_decision.
    Risk (reject) + Security injection (pause_trading) → pause_trading.
    """
    results = [
        _result("risk_auditor", veto=True, risk_flags=["extreme_spread"]),
        _result(
            "security_guardian", category="security", veto=True,
            security_flags=["metadata_injection_attempt"],
        ),
    ]
    summary = build_veto_summary(results)
    # pause_trading has higher priority than reject
    assert summary.resolved_decision == AgentDecision.PAUSE_TRADING.value
    assert summary.resolved_severity == "critical"


def test_veto_summary_to_dict_no_veto():
    """Non-vetoed summary serialises cleanly."""
    results = [_result("clean")]
    d = veto_summary_to_dict(build_veto_summary(results))
    assert d == {"vetoed": False}


def test_veto_summary_to_dict_full_structure():
    """Vetoed summary dict has all expected keys."""
    results = [
        _result("risk_auditor", veto=True, risk_flags=["invalid_price"])
    ]
    d = veto_summary_to_dict(build_veto_summary(results))
    assert d["vetoed"] is True
    assert "resolved_decision" in d
    assert "resolved_severity" in d
    assert "primary_agent" in d
    assert "primary_veto_type" in d
    assert "primary_reasoning" in d
    assert "all_vetoes" in d
    assert "all_risk_flags" in d
    assert "all_security_flags" in d


# ── classify_veto ─────────────────────────────────────────────────────────────

def test_classify_veto_security_agent_without_flags_defaults_to_pause():
    """Security agent with no specific flags falls back to pause_trading (category default)."""
    result = _result("security_guardian", category="security", veto=True)
    vc = classify_veto(result)
    assert vc.suggested_decision == AgentDecision.PAUSE_TRADING.value
    assert vc.veto_type == "security"


def test_classify_veto_risk_policy_flag_is_policy_type():
    result = _result("cro", veto=True, risk_flags=["bot_not_active"])
    vc = classify_veto(result)
    assert vc.veto_type == "policy"
    assert vc.suggested_decision == AgentDecision.WAIT.value


def test_classify_veto_unknown_agent_defaults_to_reject():
    result = _result("mystery_agent", category="unknown", veto=True)
    vc = classify_veto(result)
    assert vc.veto_type == "unknown"


# ── collect_all_flags ──────────────────────────────────────────────────────────

def test_collect_all_flags_deduplicates():
    results = [
        _result("a", risk_flags=["high_spread", "stale_data"]),
        _result("b", risk_flags=["high_spread", "low_volume"]),
        _result("c", security_flags=["metadata_injection_attempt"]),
    ]
    risk, security = collect_all_flags(results)
    # Deduplicated and sorted
    assert "high_spread" in risk
    assert risk.count("high_spread") == 1
    assert "low_volume" in risk
    assert "stale_data" in risk
    assert "metadata_injection_attempt" in security


def test_collect_all_flags_empty():
    risk, security = collect_all_flags([])
    assert risk == []
    assert security == []


def test_collect_flags_returns_sorted():
    results = [_result("a", risk_flags=["z_flag", "a_flag", "m_flag"])]
    risk, _ = collect_all_flags(results)
    assert risk == sorted(risk)


def test_collect_flags_includes_non_vetoing_agents():
    """collect_all_flags includes flags from ALL agents, not just vetoing ones."""
    results = [
        _result("agent_a", risk_flags=["stale_data"], veto=False),
        _result("agent_b", risk_flags=["extreme_spread"], veto=True),
    ]
    risk, _ = collect_all_flags(results)
    assert "stale_data" in risk
    assert "extreme_spread" in risk


# ── derive_severity_from_flags ────────────────────────────────────────────────

def test_derive_severity_injection_is_critical():
    from src.db.models import SeverityLevel
    sev = derive_severity_from_flags([], ["metadata_injection_attempt"])
    assert sev == SeverityLevel.CRITICAL


def test_derive_severity_extreme_spread_is_high():
    from src.db.models import SeverityLevel
    sev = derive_severity_from_flags(["extreme_spread"], [])
    assert sev == SeverityLevel.HIGH


def test_derive_severity_position_limit_is_low():
    from src.db.models import SeverityLevel
    sev = derive_severity_from_flags(["position_limit_reached"], [])
    assert sev == SeverityLevel.LOW


def test_derive_severity_empty_flags_is_info():
    from src.db.models import SeverityLevel
    sev = derive_severity_from_flags([], [])
    assert sev == SeverityLevel.INFO


def test_derive_severity_highest_flag_wins():
    """When mixed severity flags are present, the highest severity wins."""
    from src.db.models import SeverityLevel
    sev = derive_severity_from_flags(
        ["position_limit_reached", "extreme_spread"],  # low + high
        ["metadata_injection_attempt"],                # critical
    )
    assert sev == SeverityLevel.CRITICAL
