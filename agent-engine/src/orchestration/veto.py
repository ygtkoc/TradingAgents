"""
Veto detection and severity-aware decision mapping.

The veto system is the pipeline's hard stop mechanism.
Any agent with can_veto=True returning veto=True immediately
terminates score aggregation and forces a terminal decision.

SEVERITY MAPPING:
  security critical (injection/prompt)  → pause_trading
  risk critical (extreme conditions)    → reject
  data quality (soft issues)            → wait
  data quality (hard/corrupt data)      → reject
  manipulation high/critical            → reject
  bot policy (limit/config)             → wait
  unknown                               → reject

The first veto short-circuits the pipeline (no further agents run).
The summary collects ALL vetoing agents found so far in the result list,
so a risk agent veto immediately before security agents will still capture
any security flags already produced.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.db.models import AgentDecision, SeverityLevel
from src.logging_config import get_logger

log = get_logger(__name__)


# ── Severity classification tables ───────────────────────────────────────────

# Flag → (severity, suggested_final_decision)
# More specific entries override category-level defaults.
_FLAG_SEVERITY: dict[str, tuple[str, str]] = {
    # Prompt injection / security takeover
    "metadata_injection_attempt": ("critical", AgentDecision.PAUSE_TRADING.value),
    "agent_reasoning_injection": ("critical", AgentDecision.PAUSE_TRADING.value),
    "signal_field_injection": ("critical", AgentDecision.PAUSE_TRADING.value),
    "suspicious_score_distribution": ("high", AgentDecision.PAUSE_TRADING.value),
    "invalid_symbol_format": ("high", AgentDecision.REJECT.value),
    "invalid_exchange_format": ("high", AgentDecision.REJECT.value),
    "invalid_direction": ("high", AgentDecision.REJECT.value),
    # Data quality — hard failures
    "invalid_price": ("critical", AgentDecision.REJECT.value),
    "corrupted_ohlcv": ("critical", AgentDecision.REJECT.value),
    "critical_data_missing": ("critical", AgentDecision.REJECT.value),
    "no_market_data": ("high", AgentDecision.REJECT.value),
    # Data quality — soft failures
    "risk_assessment_impossible": ("medium", AgentDecision.WAIT.value),
    "insufficient_history": ("low", AgentDecision.WAIT.value),
    "stale_data": ("low", AgentDecision.WAIT.value),
    # Manipulation
    "extreme_spread": ("high", AgentDecision.REJECT.value),
    "extreme_volume_spike": ("high", AgentDecision.REJECT.value),
    "potential_pump": ("high", AgentDecision.REJECT.value),
    "low_volume_spike": ("medium", AgentDecision.REJECT.value),
    "ohlcv_anomaly": ("high", AgentDecision.REJECT.value),
    # Risk — policy
    "position_limit_reached": ("low", AgentDecision.WAIT.value),
    "bot_not_active": ("medium", AgentDecision.WAIT.value),
    "live_trading_disabled": ("medium", AgentDecision.WAIT.value),
    "user_trading_disabled": ("medium", AgentDecision.WAIT.value),
    "missing_bot_context": ("medium", AgentDecision.WAIT.value),
    # Risk — critical conditions
    "extreme_overbought_long": ("high", AgentDecision.REJECT.value),
    "extreme_oversold_short": ("high", AgentDecision.REJECT.value),
    "low_risk_score": ("high", AgentDecision.REJECT.value),
}

# Agent category → default (severity, decision) when no flags match
_CATEGORY_DEFAULTS: dict[str, tuple[str, str]] = {
    "security": ("critical", AgentDecision.PAUSE_TRADING.value),
    "risk": ("high", AgentDecision.REJECT.value),
    "data": ("medium", AgentDecision.REJECT.value),
    "analysis": ("medium", AgentDecision.REJECT.value),
    "critique": ("medium", AgentDecision.REJECT.value),
}


@dataclass
class VetoClassification:
    """Result of classifying a single vetoing agent's output."""
    agent_name: str
    agent_category: str
    severity: str                  # SeverityLevel value
    suggested_decision: str        # AgentDecision value
    reasoning: str
    risk_flags: list[str]
    security_flags: list[str]
    score: float | None
    confidence: float | None
    veto_type: str                 # "security" | "risk" | "data" | "policy" | "unknown"


@dataclass
class VetoSummaryResult:
    """Aggregated summary of all veto classifications in a pipeline run."""
    vetoed: bool
    # Highest-severity classification drives the final decision
    primary: VetoClassification | None
    all_vetoes: list[VetoClassification]
    # Resolved final decision based on highest severity veto
    resolved_decision: str
    resolved_severity: str
    all_risk_flags: list[str]
    all_security_flags: list[str]


def classify_veto(result: dict[str, Any]) -> VetoClassification:
    """
    Classifies a single vetoing agent result into a severity and suggested decision.

    Resolution order:
    1. Security flags take priority over risk flags
    2. Highest-severity individual flag wins within the agent
    3. Falls back to category-level default
    """
    agent_name = result.get("agent_name", "unknown")
    agent_category = result.get("agent_category", "unknown")
    risk_flags: list[str] = result.get("risk_flags", [])
    security_flags: list[str] = result.get("security_flags", [])
    reasoning = result.get("reasoning", "")[:500]

    # Determine veto_type
    if agent_category == "security" or security_flags:
        veto_type = "security"
    elif agent_category == "risk":
        # Distinguish policy vs critical risk
        policy_flags = {"position_limit_reached", "bot_not_active", "live_trading_disabled",
                        "user_trading_disabled", "missing_bot_context"}
        if any(f in policy_flags for f in risk_flags):
            veto_type = "policy"
        else:
            veto_type = "risk"
    elif agent_category == "data":
        veto_type = "data"
    else:
        veto_type = "unknown"

    # Score all flags and pick the highest severity
    severity_order = ["low", "medium", "high", "critical"]
    best_severity = "low"
    best_decision = AgentDecision.REJECT.value

    all_flags = security_flags + risk_flags
    if all_flags:
        for flag in all_flags:
            if flag in _FLAG_SEVERITY:
                flag_sev, flag_dec = _FLAG_SEVERITY[flag]
                if severity_order.index(flag_sev) > severity_order.index(best_severity):
                    best_severity = flag_sev
                    best_decision = flag_dec
    else:
        # No specific flags — use category default
        cat_sev, cat_dec = _CATEGORY_DEFAULTS.get(agent_category, ("high", AgentDecision.REJECT.value))
        best_severity = cat_sev
        best_decision = cat_dec

    # Security category always at least pause_trading
    if agent_category == "security" and best_decision == AgentDecision.REJECT.value:
        best_decision = AgentDecision.PAUSE_TRADING.value

    return VetoClassification(
        agent_name=agent_name,
        agent_category=agent_category,
        severity=best_severity,
        suggested_decision=best_decision,
        reasoning=reasoning,
        risk_flags=risk_flags,
        security_flags=security_flags,
        score=result.get("score"),
        confidence=result.get("confidence"),
        veto_type=veto_type,
    )


# ── Public API ────────────────────────────────────────────────────────────────

def check_for_veto(
    agent_results: list[dict[str, Any]]
) -> tuple[bool, str | None]:
    """
    Scans agent_results for the first veto=True result.

    Returns:
        (veto_triggered: bool, vetoing_agent_name: str | None)

    The first veto found short-circuits the pipeline. Call
    build_veto_summary() on the full result list to get all vetoes
    that ran before the cutoff.
    """
    for result in agent_results:
        if result.get("veto", False):
            agent_name = result.get("agent_name", "unknown")
            vc = classify_veto(result)
            log.warning(
                "veto.triggered",
                agent=agent_name,
                severity=vc.severity,
                suggested_decision=vc.suggested_decision,
                veto_type=vc.veto_type,
                reasoning=vc.reasoning[:200],
                risk_flags=vc.risk_flags,
                security_flags=vc.security_flags,
            )
            return True, agent_name
    return False, None


def build_veto_summary(
    agent_results: list[dict[str, Any]]
) -> VetoSummaryResult:
    """
    Builds a complete VetoSummaryResult from ALL vetoing agents in agent_results.

    If no veto was triggered, returns a VetoSummaryResult with vetoed=False.
    The resolved_decision is determined by the highest-severity veto found.

    Callers should use .resolved_decision as the pipeline's final_decision
    whenever veto_triggered=True.
    """
    severity_order = ["low", "medium", "high", "critical"]
    all_vetoes: list[VetoClassification] = []
    all_risk_flags: set[str] = set()
    all_security_flags: set[str] = set()

    for result in agent_results:
        if result.get("veto", False):
            vc = classify_veto(result)
            all_vetoes.append(vc)
            all_risk_flags.update(vc.risk_flags)
            all_security_flags.update(vc.security_flags)

    if not all_vetoes:
        return VetoSummaryResult(
            vetoed=False,
            primary=None,
            all_vetoes=[],
            resolved_decision=AgentDecision.WAIT.value,
            resolved_severity="low",
            all_risk_flags=[],
            all_security_flags=[],
        )

    # Primary = highest severity; ties broken by decision severity (pause > reject > wait)
    decision_priority = {
        AgentDecision.PAUSE_TRADING.value: 3,
        AgentDecision.REJECT.value: 2,
        AgentDecision.WAIT.value: 1,
    }

    primary = max(
        all_vetoes,
        key=lambda vc: (
            severity_order.index(vc.severity),
            decision_priority.get(vc.suggested_decision, 0),
        ),
    )

    return VetoSummaryResult(
        vetoed=True,
        primary=primary,
        all_vetoes=all_vetoes,
        resolved_decision=primary.suggested_decision,
        resolved_severity=primary.severity,
        all_risk_flags=sorted(all_risk_flags),
        all_security_flags=sorted(all_security_flags),
    )


def veto_summary_to_dict(summary: VetoSummaryResult) -> dict[str, Any]:
    """Serialises a VetoSummaryResult to a plain dict for DB/JSON storage."""
    if not summary.vetoed:
        return {"vetoed": False}

    return {
        "vetoed": True,
        "resolved_decision": summary.resolved_decision,
        "resolved_severity": summary.resolved_severity,
        "primary_agent": summary.primary.agent_name if summary.primary else None,
        "primary_veto_type": summary.primary.veto_type if summary.primary else None,
        "primary_reasoning": summary.primary.reasoning[:500] if summary.primary else "",
        "all_vetoes": [
            {
                "agent_name": vc.agent_name,
                "agent_category": vc.agent_category,
                "severity": vc.severity,
                "suggested_decision": vc.suggested_decision,
                "veto_type": vc.veto_type,
                "risk_flags": vc.risk_flags,
                "security_flags": vc.security_flags,
                "reasoning": vc.reasoning[:200],
            }
            for vc in summary.all_vetoes
        ],
        "all_risk_flags": summary.all_risk_flags,
        "all_security_flags": summary.all_security_flags,
    }


def collect_all_flags(
    agent_results: list[dict[str, Any]]
) -> tuple[list[str], list[str]]:
    """
    Collects and deduplicates all risk_flags and security_flags
    from all agent results (vetoing and non-vetoing).

    Returns:
        (risk_flags: list[str], security_flags: list[str])
    """
    seen_risk: set[str] = set()
    seen_sec: set[str] = set()

    for result in agent_results:
        for flag in result.get("risk_flags", []):
            seen_risk.add(flag)
        for flag in result.get("security_flags", []):
            seen_sec.add(flag)

    return sorted(seen_risk), sorted(seen_sec)


def derive_severity_from_flags(
    risk_flags: list[str],
    security_flags: list[str],
) -> SeverityLevel:
    """
    Returns the highest severity level implied by the given flag lists.
    Used when constructing risk_log / security_log entries.
    """
    severity_order = ["low", "medium", "high", "critical"]
    best = "info"
    for flag in risk_flags + security_flags:
        if flag in _FLAG_SEVERITY:
            sev = _FLAG_SEVERITY[flag][0]
            if sev in severity_order and (
                best == "info" or severity_order.index(sev) > severity_order.index(best)
            ):
                best = sev
    level_map = {
        "info": SeverityLevel.INFO,
        "low": SeverityLevel.LOW,
        "medium": SeverityLevel.MEDIUM,
        "high": SeverityLevel.HIGH,
        "critical": SeverityLevel.CRITICAL,
    }
    return level_map.get(best, SeverityLevel.MEDIUM)
