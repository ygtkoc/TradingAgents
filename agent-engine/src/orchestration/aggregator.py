"""
Score aggregation and final trade decision logic.

The aggregator takes all AgentOutputResult dicts from state["agent_results"],
applies per-agent weights, applies penalties, and produces a final decision.

Decision thresholds (configurable via settings):
  score >= score_threshold_open (default 70):   open_long / open_short
  score >= score_threshold_manual_review (40):  manual_approval_required
  else:                                          wait

IMPORTANT: AgentDecision.MANUAL_APPROVAL_REQUIRED maps to the exact PostgreSQL
enum value "manual_approval_required". Do NOT introduce "manual_review" — it does
not exist in the DB enum and will cause insert failures.

Approval status rules:
  paper/shadow + open_* + no manual override   → auto_approved
  paper/shadow + open_* + requires_manual      → pending
  live mode + open_*                           → pending (human approval required)
  live + requires_approval setting             → pending
  score >= manual threshold                    → pending (regardless of mode)
  wait / reject / pause_trading                → rejected (not pending)

The aggregator respects veto decisions — if any veto was set, the final
decision is taken from the VetoSummaryResult resolved_decision, never from score.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from src.config import settings
from src.db.models import AgentCategory, AgentDecision, ApprovalStatus, BotMode, TradeDirection
from src.logging_config import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class AggregationResult:
    """Output of the aggregation step."""
    aggregated_score: float
    final_decision: AgentDecision
    approval_status: ApprovalStatus
    manual_approval_required: bool
    direction: TradeDirection
    confidence: float
    reasoning: str
    score_breakdown: dict[str, float]


def aggregate(
    agent_results: list[dict[str, Any]],
    intended_direction: str,
    data_quality_penalty: float = 0.0,
    manipulation_score_penalty: float = 0.0,
    risk_score: float = 100.0,
    veto_triggered: bool = False,
    veto_resolved_decision: str | None = None,
    veto_agent_name: str | None = None,
    bot_mode: str = "paper",
    requires_manual_approval: bool = False,
    real_trading_requires_approval: bool = True,
) -> AggregationResult:
    """
    Computes the weighted aggregated score and maps it to a trade decision.

    Args:
        agent_results:                  List of AgentOutputResult.model_dump() dicts.
        intended_direction:             'long' | 'short' | 'neutral'
        data_quality_penalty:           Score deduction for data quality issues (0–50).
        manipulation_score_penalty:     Score deduction from ManipulationDetectionAgent.
        risk_score:                     Raw risk score from RiskAuditorAgent (0–100).
        veto_triggered:                 True if any veto was set.
        veto_resolved_decision:         The VetoSummaryResult.resolved_decision string.
        veto_agent_name:                Name of the primary vetoing agent.
        bot_mode:                       'paper' | 'live' | 'shadow'
        requires_manual_approval:       bot.requires_manual_approval flag.
        real_trading_requires_approval: user_settings.real_trading_requires_approval flag.

    Returns:
        AggregationResult with all decision fields populated.
    """

    direction = _str_to_direction(intended_direction)

    # ── Hard veto: use severity-resolved decision ─────────────────────────────
    if veto_triggered:
        # The resolved_decision comes from veto.py severity mapping
        decision_str = veto_resolved_decision or AgentDecision.REJECT.value
        try:
            final_decision = AgentDecision(decision_str)
        except ValueError:
            final_decision = AgentDecision.REJECT

        return AggregationResult(
            aggregated_score=-100.0,
            final_decision=final_decision,
            approval_status=ApprovalStatus.REJECTED,
            manual_approval_required=False,
            direction=direction,
            confidence=1.0,
            reasoning=(
                f"Veto by {veto_agent_name or 'unknown agent'}. "
                f"Resolved decision: {final_decision.value}."
            ),
            score_breakdown={"veto": -100.0},
        )

    # ── Separate scoring agents (analysis + critique only) ────────────────────
    SCORING_CATEGORIES = {
        AgentCategory.ANALYSIS.value,
        AgentCategory.CRITIQUE.value,
    }

    scored_results = [
        r for r in agent_results
        if r.get("agent_category") in SCORING_CATEGORIES
        and not r.get("veto", False)
        and r.get("error") is None
    ]

    score_breakdown: dict[str, float] = {}

    # ── Weighted sum ──────────────────────────────────────────────────────────
    total_weight = 0.0
    weighted_sum = 0.0

    for result in scored_results:
        agent_name = result.get("agent_name", "unknown")
        score = result.get("score", 0.0)
        weight = result.get("weight", 1.0)
        confidence = result.get("confidence", 0.5)

        effective_weight = weight * confidence
        weighted_sum += score * effective_weight
        total_weight += effective_weight
        score_breakdown[agent_name] = round(score, 2)

    raw_score = weighted_sum / total_weight if total_weight > 0 else 0.0

    # ── Apply penalties ───────────────────────────────────────────────────────
    dq_deduction = min(30.0, data_quality_penalty * 0.5)
    manip_deduction = min(40.0, manipulation_score_penalty * 0.4)
    risk_deduction = max(0.0, (100.0 - risk_score) * 0.3)

    total_penalty = dq_deduction + manip_deduction + risk_deduction
    final_score = max(-100.0, min(100.0, raw_score - total_penalty))

    score_breakdown["_raw"] = round(raw_score, 2)
    score_breakdown["_dq_penalty"] = -round(dq_deduction, 2)
    score_breakdown["_manip_penalty"] = -round(manip_deduction, 2)
    score_breakdown["_risk_penalty"] = -round(risk_deduction, 2)
    score_breakdown["_final"] = round(final_score, 2)

    # ── Map score to decision ─────────────────────────────────────────────────
    final_decision = _score_to_decision(final_score, direction)

    # ── Compute approval status ───────────────────────────────────────────────
    approval_status, manual_required = _compute_approval(
        final_decision=final_decision,
        final_score=final_score,
        bot_mode=bot_mode,
        requires_manual_approval=requires_manual_approval,
        real_trading_requires_approval=real_trading_requires_approval,
    )

    # ── Aggregate confidence ──────────────────────────────────────────────────
    confidences = [r.get("confidence", 0.5) for r in scored_results]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    reasoning = (
        f"Aggregated score: {final_score:.1f} "
        f"(raw={raw_score:.1f}, dq_pen={dq_deduction:.1f}, "
        f"manip_pen={manip_deduction:.1f}, risk_pen={risk_deduction:.1f}). "
        f"Decision: {final_decision.value}. "
        f"Approval: {approval_status.value}. "
        f"Manual required: {manual_required}. "
        f"Scoring agents: {len(scored_results)}/{len(agent_results)} total."
    )

    log.info(
        "aggregator.result",
        score=final_score,
        decision=final_decision.value,
        direction=direction.value,
        approval=approval_status.value,
        manual_required=manual_required,
        bot_mode=bot_mode,
        confidence=avg_confidence,
    )

    return AggregationResult(
        aggregated_score=final_score,
        final_decision=final_decision,
        approval_status=approval_status,
        manual_approval_required=manual_required,
        direction=direction,
        confidence=avg_confidence,
        reasoning=reasoning,
        score_breakdown=score_breakdown,
    )


def _score_to_decision(score: float, direction: TradeDirection) -> AgentDecision:
    """
    Maps a numeric score to a concrete AgentDecision.
    Does NOT set approval status — that is handled by _compute_approval().

    DB enum values used:
      "open_long", "open_short", "manual_approval_required", "wait"
    """
    if score >= settings.score_threshold_open:
        if direction == TradeDirection.LONG:
            return AgentDecision.OPEN_LONG
        elif direction == TradeDirection.SHORT:
            return AgentDecision.OPEN_SHORT
        # Neutral direction — cannot open a directional trade
        return AgentDecision.WAIT

    if score >= settings.score_threshold_manual_review:
        return AgentDecision.MANUAL_APPROVAL_REQUIRED

    return AgentDecision.WAIT


def _compute_approval(
    final_decision: AgentDecision,
    final_score: float,
    bot_mode: str,
    requires_manual_approval: bool,
    real_trading_requires_approval: bool,
) -> tuple[ApprovalStatus, bool]:
    """
    Determines approval_status and manual_approval_required.

    Rules (in priority order):
    1. Non-actionable decisions (wait/reject/pause_trading/close/reduce)
       → approval_status=rejected, manual_required=False
    2. manual_approval_required decision
       → approval_status=pending, manual_required=True
    3. Live mode (any open_* decision)
       → always pending, manual_required depends on settings
    4. Paper/shadow + open_* + no bot manual override
       → auto_approved, manual_required=False
       (The score already cleared score_threshold_open to reach open_*;
        an additional buffer here creates orphaned decisions the execution
        engine can never claim.)
    5. Fallback → pending, manual_required=True

    Returns:
        (ApprovalStatus, manual_approval_required: bool)
    """
    NON_ACTIONABLE = {
        AgentDecision.WAIT,
        AgentDecision.REJECT,
        AgentDecision.PAUSE_TRADING,
        AgentDecision.CLOSE_POSITION,
        AgentDecision.REDUCE_POSITION,
    }

    OPEN_DECISIONS = {AgentDecision.OPEN_LONG, AgentDecision.OPEN_SHORT}

    # Rule 1: Non-actionable — no approval process
    if final_decision in NON_ACTIONABLE:
        return ApprovalStatus.REJECTED, False

    # Rule 2: Explicit manual approval required
    if final_decision == AgentDecision.MANUAL_APPROVAL_REQUIRED:
        return ApprovalStatus.PENDING, True

    # Rule 3: Live mode — always requires human approval
    if bot_mode == BotMode.LIVE.value:
        manual = requires_manual_approval or real_trading_requires_approval
        return ApprovalStatus.PENDING, manual

    # Rule 4: Paper or shadow + open decision
    if final_decision in OPEN_DECISIONS:
        if requires_manual_approval:
            return ApprovalStatus.PENDING, True
        # Auto-approve for paper/shadow — no real capital at risk.
        # The score already passed score_threshold_open to reach this point,
        # so adding a further buffer here only orphans decisions that the
        # execution engine can never pick up (it requires auto_approved/approved).
        return ApprovalStatus.AUTO_APPROVED, False

    # Rule 5: Fallback
    return ApprovalStatus.PENDING, True


def _str_to_direction(direction: str) -> TradeDirection:
    if direction == "long":
        return TradeDirection.LONG
    if direction == "short":
        return TradeDirection.SHORT
    return TradeDirection.NEUTRAL
