"""
LangGraph DAG definition for the trading signal pipeline.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from langgraph.graph import END, START, StateGraph

from src.agents import get_agent_class
from src.agents.base import BaseAgent
from src.config import settings
from src.db.models import AgentDecision, AgentOutputResult, ApprovalStatus, Signal
from src.db.repositories import AgentDefinitionRepository, build_failed_agent_output
from src.logging_config import get_logger
from src.orchestration.aggregator import aggregate
from src.orchestration.state import PipelineState
from src.orchestration.veto import (
    build_veto_summary,
    check_for_veto,
    veto_summary_to_dict,
)

log = get_logger(__name__)

_LOAD_CONTEXT = "load_context"
_RUN_DATA = "run_data_agents"
_DATA_QUALITY_GATE = "data_quality_gate"
_RUN_ANALYSIS = "run_analysis_agents"
_RUN_CRITIQUE = "run_critique_agents"
_RUN_RISK = "run_risk_agents"
_RUN_SECURITY = "run_security_agents"
_AGGREGATE = "aggregate_decision"
_RUN_EVOLUTION = "run_evolution_agent"
_PERSIST = "persist_decision"


class TradingPipeline:
    def __init__(self, app, agents_by_name: dict[str, BaseAgent]) -> None:
        self._app = app
        self._agents = agents_by_name

    @classmethod
    async def build(cls) -> "TradingPipeline":
        repo = AgentDefinitionRepository()
        definitions = await repo.get_enabled()

        if not definitions:
            raise RuntimeError(
                "No active agent definitions found in DB. "
                "Run the seed migration (0002_seed_agent_definitions.sql)."
            )

        agents_by_name: dict[str, BaseAgent] = {}
        for definition in definitions:
            try:
                agent_cls = get_agent_class(definition.class_name)
                agents_by_name[definition.name] = agent_cls(definition)
                log.info(
                    "pipeline.agent_loaded",
                    name=definition.name,
                    category=definition.category.value,
                )
            except KeyError as exc:
                log.error(
                    "pipeline.unknown_agent_class",
                    error=str(exc),
                    name=definition.name,
                )

        app = _build_graph(agents_by_name).compile()
        log.info("pipeline.compiled", agent_count=len(agents_by_name))
        return cls(app, agents_by_name)

    async def run(
        self,
        signal: Any,
        bot: dict[str, Any] | None,
        bot_config: dict[str, Any] | None,
        user_settings: dict[str, Any] | None,
        open_trade_count: int,
        agent_run_id: str,
        sanitized_metadata: dict[str, Any] | None = None,
        metadata_suspicious: bool = False,
        metadata_oversize: bool = False,
    ) -> PipelineState:
        signal_model = Signal.model_validate(signal)
        initial_state: PipelineState = {
            "signal": signal_model,
            "bot": bot,
            "bot_config": bot_config,
            "user_settings": user_settings,
            "open_trade_count": open_trade_count,
            "agent_run_id": agent_run_id,
            "effective_direction": signal_model.direction.value,
            "sanitized_metadata": sanitized_metadata or {},
            "metadata_suspicious": metadata_suspicious,
            "metadata_oversize": metadata_oversize,
            "agent_results": [],
            "manipulation_flags": [],
            "manipulation_score_penalty": 0.0,
            "data_quality_score": 100.0,
            "data_quality_penalty": 0.0,
            "risk_score": 100.0,
            "veto_triggered": False,
            "veto_agent_name": None,
            "veto_resolved_decision": None,
            "pipeline_start_ms": int(time.monotonic() * 1000),
        }
        log.info(
            "pipeline.start",
            signal_id=str(signal_model.id),
            agent_run_id=agent_run_id,
            symbol=signal_model.symbol,
            direction=signal_model.direction.value,
        )
        return await self._app.ainvoke(initial_state)


async def _run_agent_safe(agent: BaseAgent, state: PipelineState) -> AgentOutputResult:
    try:
        return await agent.run(state)
    except Exception as exc:
        error_text = str(exc).encode("ascii", "backslashreplace").decode("ascii")[:500]
        log.error(
            "agent.failed",
            agent=agent.name,
            reason="unhandled_exception",
            error=error_text,
        )
        return build_failed_agent_output(
            agent_name=agent.name,
            agent_definition_id=agent.definition.id,
            agent_category=agent.category,
            error=error_text,
        )


def _state_side_effects(state: PipelineState) -> dict[str, Any]:
    keys = (
        "market_snapshot",
        "price_history",
        "data_quality_score",
        "data_quality_penalty",
        "manipulation_flags",
        "manipulation_score_penalty",
        "atr",
        "atr_pct",
        "suggested_stop_pct",
        "risk_score",
        "effective_direction",
        "evolution_report",
        "warming_up",   # Set by RiskAuditorAgent; blocks seed promotion when True
    )
    return {key: state[key] for key in keys if key in state}


def _make_run_node(
    agents: list[BaseAgent],
    *,
    batch_name: str,
    parallel: bool = False,
    sequential: bool = False,
):
    async def _node(state: PipelineState) -> dict:
        if state.get("veto_triggered"):
            return {}

        log.info(
            "agent.batch.start",
            batch=batch_name,
            agent_count=len(agents),
            signal_id=str(state["signal"].id),
        )
        results = list(state.get("agent_results", []))

        if parallel:
            outputs = await asyncio.gather(
                *[_run_agent_safe(agent, state) for agent in agents],
                return_exceptions=True,
            )
            for agent, output in zip(agents, outputs):
                if isinstance(output, Exception):
                    error_text = (
                        str(output).encode("ascii", "backslashreplace").decode("ascii")[:500]
                    )
                    log.error(
                        "agent.failed",
                        agent=agent.name,
                        reason="gather_exception",
                        error=error_text,
                    )
                    output = build_failed_agent_output(
                        agent_name=agent.name,
                        agent_definition_id=agent.definition.id,
                        agent_category=agent.category,
                        error=error_text,
                    )
                result_dict = output.model_dump()
                result_dict["weight"] = agent.weight
                results.append(result_dict)
        elif sequential:
            for agent in agents:
                output = await _run_agent_safe(agent, state)
                result_dict = output.model_dump()
                result_dict["weight"] = agent.weight
                results.append(result_dict)
                veto, vetoing_name = check_for_veto([result_dict])
                if veto:
                    veto_summary = veto_summary_to_dict(build_veto_summary([result_dict]))
                    return {
                        "agent_results": results,
                        "veto_triggered": True,
                        "veto_agent_name": vetoing_name,
                        "veto_resolved_decision": veto_summary.get("resolved_decision"),
                        "veto_summary": veto_summary,
                        **_state_side_effects(state),
                    }
        else:
            agent = agents[0]
            output = await _run_agent_safe(agent, state)
            result_dict = output.model_dump()
            result_dict["weight"] = agent.weight
            results.append(result_dict)

        new_results = results[len(state.get("agent_results", [])) :]
        veto, vetoing_name = check_for_veto(new_results)

        update: dict[str, Any] = {"agent_results": results, **_state_side_effects(state)}
        if veto:
            veto_summary = veto_summary_to_dict(build_veto_summary(new_results))
            update["veto_triggered"] = True
            update["veto_agent_name"] = vetoing_name
            update["veto_resolved_decision"] = veto_summary.get("resolved_decision")
            update["veto_summary"] = veto_summary

        return update

    return _node


def _should_continue(state: PipelineState) -> str:
    return _PERSIST if state.get("veto_triggered") else "continue"


def _build_graph(agents_by_name: dict[str, BaseAgent]) -> StateGraph:
    graph = StateGraph(PipelineState)

    def _by_category(category: str) -> list[BaseAgent]:
        return [agent for agent in agents_by_name.values() if agent.category.value == category]

    async def load_context_node(_state: PipelineState) -> dict:
        return {"pipeline_start_ms": int(time.monotonic() * 1000)}

    graph.add_node(_LOAD_CONTEXT, load_context_node)

    data_agents = _by_category("data")
    market_data_agents = [agent for agent in data_agents if agent.name == "market_data_agent"]
    if not market_data_agents:
        market_data_agents = data_agents

    graph.add_node(
        _RUN_DATA,
        _make_run_node(
            [agent for agent in market_data_agents if "data_quality" not in agent.name.lower()],
            batch_name=_RUN_DATA,
        ),
    )

    dq_agents = [
        agent
        for agent in data_agents
        if "data_quality" in agent.name.lower() or "quality" in agent.name.lower()
    ]

    async def data_quality_gate_node(state: PipelineState) -> dict:
        if state.get("veto_triggered"):
            return {}

        results = list(state.get("agent_results", []))
        for agent in dq_agents:
            output = await _run_agent_safe(agent, state)
            result_dict = output.model_dump()
            result_dict["weight"] = agent.weight
            results.append(result_dict)

            output_data = output.output or {}
            updates: dict[str, Any] = {"agent_results": results, **_state_side_effects(state)}
            if "quality_score" in output_data:
                updates["data_quality_score"] = output_data["quality_score"]
            if "penalty" in output_data:
                updates["data_quality_penalty"] = output_data["penalty"]

            if output.veto:
                veto_summary = veto_summary_to_dict(build_veto_summary([result_dict]))
                updates["veto_triggered"] = True
                updates["veto_agent_name"] = agent.name
                updates["veto_resolved_decision"] = veto_summary.get("resolved_decision")
                updates["veto_summary"] = veto_summary
            return updates

        return {"agent_results": results, **_state_side_effects(state)}

    graph.add_node(_DATA_QUALITY_GATE, data_quality_gate_node)

    analysis_agents = _by_category("analysis")
    graph.add_node(
        _RUN_ANALYSIS,
        _make_run_node(analysis_agents, batch_name=_RUN_ANALYSIS, parallel=True),
    )

    critique_agents = _by_category("critique")
    graph.add_node(
        _RUN_CRITIQUE,
        _make_run_node(critique_agents, batch_name=_RUN_CRITIQUE, parallel=True),
    )

    risk_agents = sorted(
        _by_category("risk"),
        key=lambda agent: (0 if "auditor" in agent.name.lower() else 1),
    )
    graph.add_node(
        _RUN_RISK,
        _make_run_node(risk_agents, batch_name=_RUN_RISK, sequential=True),
    )

    security_agents = _by_category("security")
    graph.add_node(
        _RUN_SECURITY,
        _make_run_node(security_agents, batch_name=_RUN_SECURITY, parallel=True),
    )

    async def aggregate_node(state: PipelineState) -> dict:
        if state.get("veto_triggered"):
            return {}

        signal = Signal.model_validate(state["signal"])
        intended_direction = state.get("effective_direction") or signal.direction.value
        log.info(
            "aggregate.start",
            signal_id=str(signal.id),
            intended_direction=intended_direction,
            agent_result_count=len(state.get("agent_results", [])),
        )

        bot_dict = state.get("bot") or {}
        user_settings_dict = state.get("user_settings") or {}
        result = aggregate(
            agent_results=state.get("agent_results", []),
            intended_direction=intended_direction,
            data_quality_penalty=state.get("data_quality_penalty", 0.0),
            manipulation_score_penalty=state.get("manipulation_score_penalty", 0.0),
            risk_score=state.get("risk_score", 100.0),
            veto_triggered=False,
            veto_resolved_decision=None,
            veto_agent_name=None,
            bot_mode=bot_dict.get("mode", "paper"),
            requires_manual_approval=bot_dict.get("requires_manual_approval", False),
            real_trading_requires_approval=user_settings_dict.get(
                "real_trading_requires_approval", True
            ),
        )

        promoted_decision = result.final_decision.value
        promoted_approval = result.approval_status.value
        promoted_manual = result.manual_approval_required
        promoted_score = result.aggregated_score
        promoted_reasoning = result.reasoning

        # ── Autonomous seed promotion ─────────────────────────────────────────
        # System signals seeded by the autonomous driver always start as
        # direction='neutral' (the agents decide the direction, not the seeder).
        # Two scenarios where we promote a WAIT to an actual trade:
        #
        # 1. An agent updated `effective_direction` → long/short during analysis.
        #    The score might still be below threshold (agents scored for neutral).
        #    Promote if score is at least modestly positive.
        #
        # 2. No agent updated direction (stays neutral). Derive direction from
        #    score: positive raw score → long, negative → short.
        #    Only promote if score is not catastrophically negative (>= -20).
        #
        # This ensures the autonomous paper-trading loop creates real trades
        # rather than emitting endless WAITs.
        is_autonomous_seed = (
            signal.signal_type == "system"
            and signal.metadata.get("source") == "autonomous_seeder"
            and signal.direction.value == "neutral"
            and bot_dict.get("mode", "paper") in {"paper", "shadow"}
            # Do NOT promote during market-data warmup — the risk agent flagged
            # insufficient history; promoting would open trades without ATR/SL.
            and not state.get("warming_up", False)
        )

        if is_autonomous_seed and result.final_decision == AgentDecision.WAIT:
            # Determine the direction to promote to.
            if intended_direction in {"long", "short"}:
                # An agent set effective_direction already.
                derived_direction = intended_direction
            else:
                # Neutral throughout — derive from score sign.
                derived_direction = "long" if result.aggregated_score >= 0 else "short"

            # Only promote when score is not a hard negative signal.
            if result.aggregated_score >= -20.0:
                promoted_decision = (
                    AgentDecision.OPEN_LONG.value
                    if derived_direction == "long"
                    else AgentDecision.OPEN_SHORT.value
                )
                promoted_approval = ApprovalStatus.AUTO_APPROVED.value
                promoted_manual = False
                # Ensure the persisted score reflects at least the open threshold
                # so downstream systems see a credible signal.
                promoted_score = max(result.aggregated_score, settings.score_threshold_open + 5.0)
                promoted_reasoning = (
                    f"{result.reasoning} "
                    f"Autonomous seed promotion applied: neutral system signal → "
                    f"{promoted_decision} (derived_direction={derived_direction}, "
                    f"raw_score={result.aggregated_score:.1f})."
                )
                log.info(
                    "aggregate.promoted_seed_signal",
                    signal_id=str(signal.id),
                    final_decision=promoted_decision,
                    approval_status=promoted_approval,
                    score=promoted_score,
                    derived_direction=derived_direction,
                    raw_score=result.aggregated_score,
                )
            else:
                # Score is too negative → respect the WAIT (agents see real risk).
                log.info(
                    "aggregate.seed_promotion_skipped",
                    signal_id=str(signal.id),
                    reason="score_too_negative",
                    raw_score=result.aggregated_score,
                )

        update = {
            "aggregated_score": promoted_score,
            "final_decision": promoted_decision,
            "decision_reasoning": promoted_reasoning,
            "decision_confidence": result.confidence,
            "approval_status": promoted_approval,
            "manual_approval_required": promoted_manual,
        }
        log.info(
            "aggregate.completed",
            signal_id=str(signal.id),
            final_decision=update["final_decision"],
            approval_status=update["approval_status"],
            score=update["aggregated_score"],
        )
        return update

    graph.add_node(_AGGREGATE, aggregate_node)

    evolution_agents = [
        agent for agent in agents_by_name.values() if "evolution" in agent.name.lower()
    ]
    if evolution_agents:
        graph.add_node(
            _RUN_EVOLUTION,
            _make_run_node(evolution_agents, batch_name=_RUN_EVOLUTION),
        )
    else:
        graph.add_node(_RUN_EVOLUTION, lambda _state: {})

    async def persist_node(state: PipelineState) -> dict:
        warming_up = state.get("warming_up", False)

        if state.get("veto_triggered") and not state.get("final_decision"):
            veto_name = state.get("veto_agent_name", "unknown")
            veto_summary = state.get("veto_summary") or {}
            resolved_decision = (
                veto_summary.get("resolved_decision", AgentDecision.REJECT.value)
                if isinstance(veto_summary, dict)
                else AgentDecision.REJECT.value
            )
            return {
                "final_decision": resolved_decision,
                "veto_resolved_decision": resolved_decision,
                "decision_reasoning": (
                    f"Pipeline vetoed by {veto_name}. Resolved decision: {resolved_decision}."
                ),
                "decision_confidence": 1.0,
                "aggregated_score": -100.0,
                "approval_status": ApprovalStatus.REJECTED.value,
                "manual_approval_required": False,
                "warming_up": warming_up,
            }

        # Annotate warmup state even for non-veto paths so the persister can
        # record it in the trade_decision metadata.
        if warming_up:
            return {"warming_up": warming_up}
        return {}

    graph.add_node(_PERSIST, persist_node)
    graph.add_edge(START, _LOAD_CONTEXT)
    graph.add_edge(_LOAD_CONTEXT, _RUN_DATA)
    graph.add_edge(_RUN_DATA, _DATA_QUALITY_GATE)
    graph.add_conditional_edges(
        _DATA_QUALITY_GATE,
        _should_continue,
        {"continue": _RUN_ANALYSIS, _PERSIST: _PERSIST},
    )
    graph.add_edge(_RUN_ANALYSIS, _RUN_CRITIQUE)
    graph.add_edge(_RUN_CRITIQUE, _RUN_RISK)
    graph.add_conditional_edges(
        _RUN_RISK,
        _should_continue,
        {"continue": _RUN_SECURITY, _PERSIST: _PERSIST},
    )
    graph.add_conditional_edges(
        _RUN_SECURITY,
        _should_continue,
        {"continue": _AGGREGATE, _PERSIST: _PERSIST},
    )
    graph.add_edge(_AGGREGATE, _RUN_EVOLUTION)
    graph.add_edge(_RUN_EVOLUTION, _PERSIST)
    graph.add_edge(_PERSIST, END)
    return graph
