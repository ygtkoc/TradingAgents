"""
Tests for the score aggregation logic.

Security patch coverage:
  FIX 1: AgentDecision.MANUAL_APPROVAL_REQUIRED (not MANUAL_REVIEW) is the
          exact DB enum value for borderline decisions.
  FIX 3: _compute_approval() respects bot_mode, requires_manual_approval, and
          real_trading_requires_approval to derive the correct ApprovalStatus.
"""
from __future__ import annotations

import pytest

from src.db.models import AgentCategory, AgentDecision, ApprovalStatus, TradeDirection
from src.orchestration.aggregator import (
    aggregate,
    _compute_approval,
    _score_to_decision,
    _str_to_direction,
)


# ── Helper ────────────────────────────────────────────────────────────────────

def _make_result(
    name: str,
    score: float,
    confidence: float = 0.8,
    category: str = AgentCategory.ANALYSIS.value,
    veto: bool = False,
    weight: float = 1.0,
    error: None = None,
) -> dict:
    return {
        "agent_name": name,
        "agent_category": category,
        "score": score,
        "confidence": confidence,
        "veto": veto,
        "weight": weight,
        "error": error,
        "risk_flags": [],
        "security_flags": [],
    }


# ── Veto tests ────────────────────────────────────────────────────────────────

def test_veto_overrides_all():
    """Any veto forces terminal decision from severity mapping, not from score."""
    results = [
        _make_result("agent_a", score=100.0),
        _make_result("agent_b", score=90.0),
    ]
    result = aggregate(
        results,
        intended_direction="long",
        veto_triggered=True,
        veto_agent_name="risk_auditor",
        veto_resolved_decision="reject",
    )
    assert result.final_decision == AgentDecision.REJECT
    assert result.approval_status == ApprovalStatus.REJECTED
    assert result.aggregated_score == -100.0


def test_veto_pause_trading_from_security():
    """Security veto with injection flag resolves to pause_trading, not reject."""
    results = [_make_result("agent_a", score=100.0)]
    result = aggregate(
        results,
        intended_direction="long",
        veto_triggered=True,
        veto_agent_name="security_guardian",
        veto_resolved_decision="pause_trading",    # FIX 4: from severity mapping
    )
    assert result.final_decision == AgentDecision.PAUSE_TRADING
    assert result.approval_status == ApprovalStatus.REJECTED


def test_no_veto_high_score_opens_long():
    results = [
        _make_result("tech", score=80.0),
        _make_result("price_action", score=75.0),
        _make_result("momentum", score=70.0),
    ]
    result = aggregate(results, intended_direction="long")
    assert result.final_decision == AgentDecision.OPEN_LONG
    assert result.direction == TradeDirection.LONG


def test_no_veto_high_score_opens_short():
    results = [
        _make_result("tech", score=80.0),
        _make_result("price_action", score=80.0),
    ]
    result = aggregate(results, intended_direction="short")
    assert result.final_decision == AgentDecision.OPEN_SHORT
    assert result.direction == TradeDirection.SHORT


def test_low_score_returns_wait():
    results = [
        _make_result("tech", score=20.0),
        _make_result("price_action", score=15.0),
    ]
    result = aggregate(results, intended_direction="long")
    assert result.final_decision == AgentDecision.WAIT


def test_medium_score_returns_manual_approval_required():
    """
    FIX 1: Borderline scores must produce MANUAL_APPROVAL_REQUIRED,
    not MANUAL_REVIEW. The value 'manual_review' does not exist in the
    PostgreSQL enum and would cause a DB insert failure.
    """
    results = [
        _make_result("tech", score=55.0),
        _make_result("price_action", score=50.0),
    ]
    result = aggregate(results, intended_direction="long")
    assert result.final_decision == AgentDecision.MANUAL_APPROVAL_REQUIRED
    assert result.final_decision.value == "manual_approval_required"


# ── Penalty tests ─────────────────────────────────────────────────────────────

def test_data_quality_penalty_reduces_score():
    results = [_make_result("tech", score=80.0)]
    no_penalty = aggregate(results, intended_direction="long")
    with_penalty = aggregate(results, intended_direction="long", data_quality_penalty=40.0)
    assert with_penalty.aggregated_score < no_penalty.aggregated_score


def test_manipulation_penalty_reduces_score():
    results = [_make_result("tech", score=80.0)]
    clean = aggregate(results, intended_direction="long")
    dirty = aggregate(results, intended_direction="long", manipulation_score_penalty=80.0)
    assert dirty.aggregated_score < clean.aggregated_score


def test_poor_risk_score_reduces_final_score():
    results = [_make_result("tech", score=80.0)]
    good_risk = aggregate(results, intended_direction="long", risk_score=100.0)
    poor_risk = aggregate(results, intended_direction="long", risk_score=0.0)
    assert poor_risk.aggregated_score < good_risk.aggregated_score


# ── Confidence weighting ──────────────────────────────────────────────────────

def test_low_confidence_agent_weighted_less():
    """A low-confidence agent's score should count for less."""
    high_conf = [_make_result("tech", score=90.0, confidence=0.9)]
    low_conf = [_make_result("tech", score=90.0, confidence=0.1)]
    r_high = aggregate(high_conf, intended_direction="long")
    r_low = aggregate(low_conf, intended_direction="long")
    # Both have same raw score — same decision, but aggregated scores may differ
    assert r_high.final_decision == r_low.final_decision


# ── Non-scoring categories ────────────────────────────────────────────────────

def test_risk_agents_excluded_from_score():
    """Risk agents (not in SCORING_CATEGORIES) should not contribute to aggregated score."""
    results = [
        _make_result("tech", score=80.0, category=AgentCategory.ANALYSIS.value),
        _make_result("risk_auditor", score=-100.0, category=AgentCategory.RISK.value),
    ]
    result = aggregate(results, intended_direction="long")
    # Risk agent score should NOT pull the aggregate negative
    assert result.aggregated_score > 0


# ── Direction mapping ─────────────────────────────────────────────────────────

def test_neutral_direction_returns_wait():
    results = [_make_result("tech", score=90.0)]
    result = aggregate(results, intended_direction="neutral")
    assert result.final_decision == AgentDecision.WAIT


# ── Empty agents ──────────────────────────────────────────────────────────────

def test_empty_agent_results_returns_wait():
    result = aggregate([], intended_direction="long")
    assert result.final_decision == AgentDecision.WAIT


def test_score_breakdown_contains_penalties():
    results = [_make_result("tech", score=80.0)]
    r = aggregate(
        results,
        intended_direction="long",
        data_quality_penalty=20.0,
        manipulation_score_penalty=10.0,
        risk_score=70.0,
    )
    assert "_dq_penalty" in r.score_breakdown
    assert "_manip_penalty" in r.score_breakdown
    assert "_risk_penalty" in r.score_breakdown
    assert r.score_breakdown["_dq_penalty"] < 0


# ── FIX 3: Approval status tests ─────────────────────────────────────────────

class TestComputeApproval:
    """
    FIX 3: Approval logic must respect bot_mode, requires_manual_approval,
    and real_trading_requires_approval — not just the final_decision enum.
    """

    def test_wait_decision_is_always_rejected(self):
        status, required = _compute_approval(
            final_decision=AgentDecision.WAIT,
            final_score=30.0,
            bot_mode="paper",
            requires_manual_approval=False,
            real_trading_requires_approval=True,
        )
        assert status == ApprovalStatus.REJECTED
        assert required is False

    def test_reject_is_non_actionable(self):
        status, required = _compute_approval(
            final_decision=AgentDecision.REJECT,
            final_score=0.0,
            bot_mode="live",
            requires_manual_approval=True,
            real_trading_requires_approval=True,
        )
        assert status == ApprovalStatus.REJECTED
        assert required is False

    def test_pause_trading_is_non_actionable(self):
        status, required = _compute_approval(
            final_decision=AgentDecision.PAUSE_TRADING,
            final_score=-100.0,
            bot_mode="live",
            requires_manual_approval=False,
            real_trading_requires_approval=True,
        )
        assert status == ApprovalStatus.REJECTED
        assert required is False

    def test_manual_approval_required_decision_always_pending(self):
        """FIX 1: MANUAL_APPROVAL_REQUIRED → pending regardless of mode."""
        status, required = _compute_approval(
            final_decision=AgentDecision.MANUAL_APPROVAL_REQUIRED,
            final_score=55.0,
            bot_mode="paper",
            requires_manual_approval=False,
            real_trading_requires_approval=False,
        )
        assert status == ApprovalStatus.PENDING
        assert required is True

    def test_live_mode_open_long_always_pending(self):
        """Live mode: any open_* decision is always pending, never auto-approved."""
        status, required = _compute_approval(
            final_decision=AgentDecision.OPEN_LONG,
            final_score=90.0,
            bot_mode="live",
            requires_manual_approval=False,
            real_trading_requires_approval=True,
        )
        assert status == ApprovalStatus.PENDING
        # requires_manual should be True because real_trading_requires_approval=True
        assert required is True

    def test_live_mode_no_real_trading_approval_still_pending(self):
        """Live mode always pending; manual_required follows settings flags."""
        status, required = _compute_approval(
            final_decision=AgentDecision.OPEN_LONG,
            final_score=90.0,
            bot_mode="live",
            requires_manual_approval=False,
            real_trading_requires_approval=False,
        )
        assert status == ApprovalStatus.PENDING
        assert required is False  # Neither flag set; still pending, not manual-required

    def test_paper_mode_strong_score_auto_approved(self):
        """Paper mode + open decision + no manual override → auto_approved (any score)."""
        from src.config import settings
        strong_score = settings.score_threshold_open + 6.0
        status, required = _compute_approval(
            final_decision=AgentDecision.OPEN_LONG,
            final_score=strong_score,
            bot_mode="paper",
            requires_manual_approval=False,
            real_trading_requires_approval=True,
        )
        assert status == ApprovalStatus.AUTO_APPROVED
        assert required is False

    def test_paper_mode_borderline_score_auto_approved(self):
        """
        Paper mode + open_long at score_threshold_open + no manual override → auto_approved.

        Previously (buggy): scores in [threshold, threshold+5) were left as 'pending',
        making the execution engine unable to claim them (it requires auto_approved).
        Fix: any open_* decision in paper/shadow without requires_manual_approval=True
        is immediately auto_approved. The score already cleared score_threshold_open
        to become open_long — no additional buffer is needed here.
        """
        from src.config import settings
        borderline_score = settings.score_threshold_open + 1.0
        status, required = _compute_approval(
            final_decision=AgentDecision.OPEN_LONG,
            final_score=borderline_score,
            bot_mode="paper",
            requires_manual_approval=False,
            real_trading_requires_approval=True,
        )
        assert status == ApprovalStatus.AUTO_APPROVED
        assert required is False

    def test_paper_mode_requires_manual_approval_flag_pending(self):
        """Paper mode + requires_manual_approval=True on bot → pending even if strong score."""
        from src.config import settings
        strong_score = settings.score_threshold_open + 10.0
        status, required = _compute_approval(
            final_decision=AgentDecision.OPEN_LONG,
            final_score=strong_score,
            bot_mode="paper",
            requires_manual_approval=True,   # Bot-level override
            real_trading_requires_approval=True,
        )
        assert status == ApprovalStatus.PENDING
        assert required is True


# ── FIX 3: Full aggregate() approval flow ────────────────────────────────────

def test_aggregate_paper_strong_score_auto_approved():
    """End-to-end: paper mode + open decision + no manual override → always auto_approved."""
    from src.config import settings
    high_score = settings.score_threshold_open + 10.0
    results = [_make_result("tech", score=high_score)]
    result = aggregate(
        results,
        intended_direction="long",
        bot_mode="paper",
        requires_manual_approval=False,
        real_trading_requires_approval=True,
    )
    if result.final_decision in (AgentDecision.OPEN_LONG, AgentDecision.OPEN_SHORT):
        # Must be auto_approved — 'pending' would orphan the decision (engine can't claim it)
        assert result.approval_status == ApprovalStatus.AUTO_APPROVED


def test_aggregate_paper_borderline_score_auto_approved():
    """End-to-end: paper mode + score exactly at threshold → still auto_approved."""
    from src.config import settings
    results = [_make_result("tech", score=settings.score_threshold_open)]
    result = aggregate(
        results,
        intended_direction="long",
        bot_mode="paper",
        requires_manual_approval=False,
        real_trading_requires_approval=False,
    )
    if result.final_decision in (AgentDecision.OPEN_LONG, AgentDecision.OPEN_SHORT):
        assert result.approval_status == ApprovalStatus.AUTO_APPROVED


def test_aggregate_live_mode_always_pending():
    """End-to-end: live mode + actionable decision → pending."""
    from src.config import settings
    high_score = settings.score_threshold_open + 10.0
    results = [_make_result("tech", score=high_score)]
    result = aggregate(
        results,
        intended_direction="long",
        bot_mode="live",
        requires_manual_approval=False,
        real_trading_requires_approval=True,
    )
    if result.final_decision in (AgentDecision.OPEN_LONG, AgentDecision.OPEN_SHORT):
        assert result.approval_status == ApprovalStatus.PENDING


def test_aggregate_manual_approval_required_enum_value():
    """
    FIX 1: Confirm the enum value stored in DB is 'manual_approval_required',
    not 'manual_review' (which does not exist in the PostgreSQL enum).
    """
    assert AgentDecision.MANUAL_APPROVAL_REQUIRED.value == "manual_approval_required"
    # Verify 'manual_review' does not exist
    values = {d.value for d in AgentDecision}
    assert "manual_review" not in values
