"""
System Evolution agent.
Observes pipeline run statistics and emits a performance report
that can be persisted to system_evolution_reports for offline analysis.

This agent does NOT affect the trade decision — it always returns WAIT
and a neutral score. It is an observability component, not a decision-maker.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.agents.base import BaseAgent
from src.db.models import AgentDecision, AgentOutputResult

if TYPE_CHECKING:
    from src.orchestration.state import PipelineState


class SystemEvolutionAgent(BaseAgent):
    """
    Aggregates run-level statistics and emits a structured evolution report.

    Metrics captured:
    - Agent scores distribution
    - Risk flags frequency
    - Veto triggers
    - Pipeline duration
    - Score vs final_decision alignment
    - Data quality trend

    The report is written to state["evolution_report"] so the orchestrator
    can persist it via SystemEvolutionReportInsert.
    """

    async def _execute(self, state: "PipelineState") -> AgentOutputResult:
        signal = state["signal"]
        agent_results: list[dict[str, Any]] = state.get("agent_results", [])
        pipeline_start_ms = state.get("pipeline_start_ms", 0)

        import time
        now_ms = int(time.monotonic() * 1000)
        pipeline_duration_ms = now_ms - pipeline_start_ms if pipeline_start_ms else None

        # ── Score distribution ────────────────────────────────────────────────
        scores = [r["score"] for r in agent_results if "score" in r]
        avg_score = sum(scores) / len(scores) if scores else 0.0
        min_score = min(scores) if scores else 0.0
        max_score = max(scores) if scores else 0.0

        # ── Risk flags frequency ──────────────────────────────────────────────
        all_risk_flags: list[str] = []
        all_security_flags: list[str] = []
        for r in agent_results:
            all_risk_flags.extend(r.get("risk_flags", []))
            all_security_flags.extend(r.get("security_flags", []))

        risk_flag_counts: dict[str, int] = {}
        for flag in all_risk_flags:
            risk_flag_counts[flag] = risk_flag_counts.get(flag, 0) + 1

        # ── Veto summary ──────────────────────────────────────────────────────
        veto_agents = [r["agent_name"] for r in agent_results if r.get("veto")]
        veto_triggered = len(veto_agents) > 0

        # ── Agent timing breakdown ────────────────────────────────────────────
        timing: dict[str, int] = {}
        for r in agent_results:
            name = r.get("agent_name", "unknown")
            dur = r.get("duration_ms")
            if dur is not None:
                timing[name] = dur

        # ── Category breakdown ────────────────────────────────────────────────
        category_scores: dict[str, list[float]] = {}
        for r in agent_results:
            cat = r.get("agent_category", "unknown")
            s = r.get("score")
            if s is not None:
                category_scores.setdefault(cat, []).append(s)

        category_avg: dict[str, float] = {
            cat: sum(vals) / len(vals) for cat, vals in category_scores.items()
        }

        # ── Final decision alignment ──────────────────────────────────────────
        final_decision = state.get("final_decision", "unknown")
        aggregated_score = state.get("aggregated_score", 0.0)
        direction = state.get("effective_direction") or (
            signal.direction.value if signal.direction else "unknown"
        )

        # Alignment = final decision matches the direction suggested by aggregated_score
        if aggregated_score >= 70 and final_decision in ("open_long", "open_short"):
            alignment = "strong_alignment"
        elif aggregated_score < 10 and final_decision in ("wait", "reject"):
            alignment = "correct_rejection"
        elif aggregated_score >= 70 and final_decision in ("wait", "reject"):
            alignment = "missed_trade"  # Might be due to veto
        elif aggregated_score < 10 and final_decision in ("open_long", "open_short"):
            alignment = "low_confidence_trade"  # Risky
        else:
            alignment = "normal"

        # ── Build evolution report ────────────────────────────────────────────
        report: dict[str, Any] = {
            "signal_id": str(signal.id),
            "symbol": signal.symbol,
            "exchange": signal.exchange,
            "direction": direction,
            "final_decision": final_decision,
            "aggregated_score": aggregated_score,
            "decision_alignment": alignment,
            "veto_triggered": veto_triggered,
            "veto_agents": veto_agents,
            "agent_count": len(agent_results),
            "score_distribution": {
                "avg": round(avg_score, 2),
                "min": round(min_score, 2),
                "max": round(max_score, 2),
            },
            "category_avg_scores": {k: round(v, 2) for k, v in category_avg.items()},
            "risk_flag_counts": risk_flag_counts,
            "security_flags": list(set(all_security_flags)),
            "data_quality_score": state.get("data_quality_score"),
            "risk_score": state.get("risk_score"),
            "manipulation_score_penalty": state.get("manipulation_score_penalty", 0.0),
            "agent_timing_ms": timing,
            "pipeline_duration_ms": pipeline_duration_ms,
        }

        state["evolution_report"] = report

        return self._make_result(
            decision=AgentDecision.WAIT,
            score=0.0,
            confidence=1.0,
            reasoning=(
                f"System evolution report generated. "
                f"Pipeline: {pipeline_duration_ms}ms, "
                f"{len(agent_results)} agents, "
                f"avg_score={avg_score:.1f}, "
                f"veto={veto_triggered}, "
                f"alignment={alignment}"
            ),
            output=report,
        )
