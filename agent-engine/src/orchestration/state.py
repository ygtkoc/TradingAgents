"""
Pipeline state definition.

PipelineState is the single shared mutable dict that flows through
the entire LangGraph DAG. Every node reads from and writes to this dict.

Design rules:
  - All keys are optional except "signal" (injected before graph entry).
  - Agents MUST NOT delete keys set by earlier agents.
  - Agents MUST use .get() with safe defaults when reading optional keys.
  - The state is NOT persisted between runs — it is ephemeral per signal.
  - Sensitive values (keys, secrets) must NEVER be placed in state.
  - signal.metadata is UNTRUSTED. Agents must read state["sanitized_metadata"],
    never state["signal"]["metadata"], for content decisions.
"""
from __future__ import annotations

from typing import Any, Optional
from typing_extensions import TypedDict


class PipelineState(TypedDict, total=False):
    """
    Typed dictionary for the LangGraph pipeline state.

    Fields are grouped by the stage that populates them.
    All fields are optional (total=False) except where noted in comments.
    """

    # ── Injected by the orchestrator before graph entry (REQUIRED) ────────────
    signal: Any                          # Signal model instance (dict form)
    bot: Optional[dict[str, Any]]        # Bot model dict
    bot_config: Optional[dict[str, Any]] # BotConfig model dict
    user_settings: Optional[dict[str, Any]]
    open_trade_count: int
    effective_direction: str             # long / short / neutral, derived when needed

    # ── Metadata safety (set by orchestrator, BEFORE graph entry) ─────────────
    # Agents must read sanitized_metadata, never signal["metadata"] directly.
    sanitized_metadata: dict[str, Any]   # Size-limited, field-filtered copy of signal.metadata
    metadata_suspicious: bool            # True if raw metadata triggered injection scan
    metadata_oversize: bool              # True if raw metadata exceeded size limit

    # ── Populated by MarketDataAgent ──────────────────────────────────────────
    market_snapshot: Optional[dict[str, Any]]   # MarketSnapshot model dict
    price_history: list[dict[str, Any]]          # List of MarketSnapshot model dicts

    # ── Populated by DataQualityAgent ─────────────────────────────────────────
    data_quality_score: float            # 0–100
    data_quality_penalty: float          # Deduction applied to final score

    # ── Populated by analysis/critique agents ────────────────────────────────
    manipulation_flags: list[str]        # Accumulated by ManipulationDetectionAgent
    manipulation_score_penalty: float    # > 0 means manipulation suspected

    # ── Populated by RiskAuditorAgent ─────────────────────────────────────────
    atr: Optional[float]
    atr_pct: Optional[float]
    suggested_stop_pct: Optional[float]
    risk_score: float                    # 0–100
    # True when history < candles_required (paper warmup mode). Set by
    # RiskAuditorAgent. Prevents seed-promotion so the pipeline records WAIT
    # instead of forcing an open-trade decision with insufficient data.
    warming_up: bool

    # ── Accumulated by all agents (appended in order) ────────────────────────
    agent_results: list[dict[str, Any]]  # List of AgentOutputResult.model_dump()

    # ── Populated by the aggregator ──────────────────────────────────────────
    aggregated_score: float              # Final weighted score (-100 to 100)
    final_decision: str                  # AgentDecision.value string
    decision_reasoning: str
    decision_confidence: float
    approval_status: str                 # ApprovalStatus.value string
    manual_approval_required: bool       # Whether a human must approve this decision

    # ── Veto state ────────────────────────────────────────────────────────────
    veto_triggered: bool                 # Set to True when any veto fires
    veto_agent_name: Optional[str]       # Name of the primary vetoing agent
    veto_resolved_decision: Optional[str] # AgentDecision.value from severity mapping
    veto_summary: Optional[dict[str, Any]] # Full VetoSummaryResult as dict

    # ── Pipeline metadata ─────────────────────────────────────────────────────
    pipeline_start_ms: int               # monotonic timestamp in ms at graph entry
    agent_run_id: Optional[str]          # UUID of the AgentRun DB row

    # ── Populated by SystemEvolutionAgent ────────────────────────────────────
    evolution_report: Optional[dict[str, Any]]
