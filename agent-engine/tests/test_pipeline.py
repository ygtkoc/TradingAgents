"""
Integration-style tests for the full pipeline.

These tests run the LangGraph pipeline end-to-end with mocked DB calls.
The actual LangGraph execution, agent logic, and score aggregation are all real.
Only the database reads/writes are mocked.

Security patch coverage:
  FIX 2: pipeline.run() now accepts sanitized_metadata, metadata_suspicious,
          metadata_oversize — all set by the orchestrator before graph entry.
  FIX 3: final_decision valid values no longer include "manual_review";
          borderline scores produce "manual_approval_required" (exact DB value).
  FIX 4: Veto-resolved decisions use severity mapping (pause_trading/reject/wait)
          rather than a hardcoded "reject".
  FIX 6: Pipeline states carry sanitized_metadata / metadata_suspicious fields;
          agents must read these, never signal["metadata"].
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from src.db.models import AgentDecision, AgentDefinition, AgentCategory
from src.orchestration.graph import TradingPipeline
from tests.conftest import make_agent_definition, make_signal, make_snapshots_series


# ── Valid final_decision values (exact PostgreSQL enum) ───────────────────────
# FIX 3: "manual_review" does NOT exist in the DB enum. Only these values are valid.
_VALID_DECISIONS = frozenset({
    "open_long",
    "open_short",
    "wait",
    "reject",
    "manual_approval_required",   # FIX 1/3: was "manual_review" — that value never existed in DB
    "pause_trading",
    "close_position",
    "reduce_position",
})


# ── Agent definition fixtures ─────────────────────────────────────────────────

def _all_definitions() -> list[AgentDefinition]:
    """Minimal set of agent definitions for a full pipeline run."""
    return [
        make_agent_definition(
            name="market_data_agent",
            category=AgentCategory.DATA,
            class_name="MarketDataAgent",
            default_weight=1.0,
        ),
        make_agent_definition(
            name="data_quality_agent",
            category=AgentCategory.DATA,
            can_veto=True,
            class_name="DataQualityAgent",
            default_weight=1.0,
        ),
        make_agent_definition(
            name="technical_analysis_agent",
            category=AgentCategory.ANALYSIS,
            class_name="TechnicalAnalysisAgent",
            default_weight=1.5,
        ),
        make_agent_definition(
            name="price_action_agent",
            category=AgentCategory.ANALYSIS,
            class_name="PriceActionAgent",
            default_weight=1.2,
        ),
        make_agent_definition(
            name="momentum_agent",
            category=AgentCategory.ANALYSIS,
            class_name="MomentumAgent",
            default_weight=1.0,
        ),
        make_agent_definition(
            name="contrarian_agent",
            category=AgentCategory.CRITIQUE,
            class_name="ContrarianAgent",
            default_weight=0.8,
        ),
        make_agent_definition(
            name="manipulation_detection_agent",
            category=AgentCategory.CRITIQUE,
            class_name="ManipulationDetectionAgent",
            default_weight=0.8,
        ),
        make_agent_definition(
            name="risk_auditor_agent",
            category=AgentCategory.RISK,
            can_veto=True,
            class_name="RiskAuditorAgent",
            default_weight=1.0,
        ),
        make_agent_definition(
            name="chief_risk_officer_agent",
            category=AgentCategory.RISK,
            can_veto=True,
            class_name="ChiefRiskOfficerAgent",
            default_weight=1.0,
        ),
        make_agent_definition(
            name="security_guardian_agent",
            category=AgentCategory.SECURITY,
            can_veto=True,
            class_name="SecurityGuardianAgent",
            default_weight=1.0,
        ),
        make_agent_definition(
            name="prompt_injection_defense_agent",
            category=AgentCategory.SECURITY,
            can_veto=True,
            class_name="PromptInjectionDefenseAgent",
            default_weight=1.0,
        ),
        make_agent_definition(
            name="system_evolution_agent",
            category=AgentCategory.SYSTEM_EVOLUTION,
            class_name="SystemEvolutionAgent",
            default_weight=0.0,
        ),
    ]


@pytest.fixture
def mock_repo():
    """Patches AgentDefinitionRepository.get_enabled to return test definitions."""
    definitions = _all_definitions()
    with patch("src.orchestration.graph.AgentDefinitionRepository") as MockRepoClass:
        instance = MockRepoClass.return_value
        instance.get_enabled = AsyncMock(return_value=definitions)
        yield instance


@pytest.fixture
def mock_market_data(btc_snapshots):
    """Patches market data service functions to return synthetic snapshots."""
    with patch(
        "src.services.market_data.get_latest_snapshot",
        new_callable=AsyncMock,
        return_value=btc_snapshots[0],
    ) as mock_snapshot, patch(
        "src.services.market_data.get_price_history",
        new_callable=AsyncMock,
        return_value=btc_snapshots,
    ) as mock_history:
        yield mock_snapshot, mock_history


@pytest.fixture
def bot_context():
    """Returns minimal bot + config + user_settings dicts."""
    bot_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    return (
        {
            "id": bot_id,
            "user_id": user_id,
            "name": "TestBot",
            "status": "active",
            "mode": "paper",
            "real_trading_enabled": False,
            "requires_manual_approval": False,
            "max_open_positions": 3,
            "max_position_size_pct": 5.0,
            "risk_per_trade_pct": 1.0,
            "max_daily_loss_pct": 5.0,
            "base_currency": "USDT",
            "trading_pairs": [],
            "active_config_id": str(uuid.uuid4()),
            "exchange_account_id": None,
            "is_archived": False,
        },
        {
            "id": str(uuid.uuid4()),
            "bot_id": bot_id,
            "user_id": user_id,
            "version": 1,
            "config": {"max_concurrent_trades": 3, "max_position_size_pct": 5.0},
            "is_active": True,
        },
        {
            "user_id": user_id,
            "trading_enabled": True,
            "real_trading_requires_approval": True,
            "created_at": "2025-01-01T00:00:00+00:00",
            "updated_at": "2025-01-01T00:00:00+00:00",
        },
    )


# ── Pipeline build test ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_builds_successfully(mock_repo):
    pipeline = await TradingPipeline.build()
    assert pipeline is not None
    assert pipeline._app is not None
    assert len(pipeline._agents) > 0


# ── Full pipeline run ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_completes_for_long_signal(mock_repo, mock_market_data, bot_context):
    """Full pipeline run for a healthy long signal — should produce a valid decision."""
    pipeline = await TradingPipeline.build()
    signal = make_signal(direction="long")
    bot, config, user_settings = bot_context

    state = await pipeline.run(
        signal=signal.model_dump(),
        bot=bot,
        bot_config=config,
        user_settings=user_settings,
        open_trade_count=0,
        agent_run_id="test-run-id",
        # FIX 6: Always pass metadata safety fields
        sanitized_metadata={"source": "tradingview"},
        metadata_suspicious=False,
        metadata_oversize=False,
    )

    assert "final_decision" in state
    # FIX 3: "manual_review" is NOT a valid DB enum value — use _VALID_DECISIONS
    assert state["final_decision"] in _VALID_DECISIONS, (
        f"final_decision '{state['final_decision']}' is not a valid PostgreSQL enum value"
    )
    assert "aggregated_score" in state
    assert len(state.get("agent_results", [])) > 0


@pytest.mark.asyncio
async def test_pipeline_final_decision_never_manual_review(mock_repo, mock_market_data, bot_context):
    """
    FIX 1/3: 'manual_review' must never appear as a final_decision.
    The correct value is 'manual_approval_required'.
    """
    pipeline = await TradingPipeline.build()
    signal = make_signal(direction="long")
    bot, config, user_settings = bot_context

    state = await pipeline.run(
        signal=signal.model_dump(),
        bot=bot,
        bot_config=config,
        user_settings=user_settings,
        open_trade_count=0,
        agent_run_id="test-run-id",
        sanitized_metadata={},
        metadata_suspicious=False,
        metadata_oversize=False,
    )

    assert state.get("final_decision") != "manual_review", (
        "final_decision='manual_review' is not a valid DB enum value. "
        "Use 'manual_approval_required'."
    )


@pytest.mark.asyncio
async def test_pipeline_includes_approval_status(mock_repo, mock_market_data, bot_context):
    """
    FIX 3: Pipeline must populate approval_status and manual_approval_required.
    """
    pipeline = await TradingPipeline.build()
    signal = make_signal(direction="long")
    bot, config, user_settings = bot_context

    state = await pipeline.run(
        signal=signal.model_dump(),
        bot=bot,
        bot_config=config,
        user_settings=user_settings,
        open_trade_count=0,
        agent_run_id="test-run-id",
        sanitized_metadata={},
        metadata_suspicious=False,
        metadata_oversize=False,
    )

    assert "approval_status" in state
    assert state["approval_status"] in {
        "pending", "approved", "rejected", "auto_approved", "expired"
    }
    assert "manual_approval_required" in state
    assert isinstance(state["manual_approval_required"], bool)


@pytest.mark.asyncio
async def test_injection_in_symbol_triggers_veto(mock_repo, mock_market_data, bot_context):
    """A signal with SQL injection in the symbol should be vetoed."""
    pipeline = await TradingPipeline.build()
    signal = make_signal(direction="long", symbol="'; DROP TABLE signals; --")
    bot, config, user_settings = bot_context

    state = await pipeline.run(
        signal=signal.model_dump(),
        bot=bot,
        bot_config=config,
        user_settings=user_settings,
        open_trade_count=0,
        agent_run_id="test-run-id",
        sanitized_metadata={},
        metadata_suspicious=False,
        metadata_oversize=False,
    )

    assert state.get("veto_triggered") is True
    # FIX 4: Veto decision comes from severity mapping; invalid symbol → reject
    assert state.get("final_decision") in ("reject", "pause_trading")


@pytest.mark.asyncio
async def test_metadata_suspicious_flag_propagated_to_state(mock_repo, mock_market_data, bot_context):
    """
    FIX 6: metadata_suspicious=True must be stored in state and visible to agents.
    Agents read state["metadata_suspicious"], not signal["metadata"].
    The SecurityGuardianAgent should veto when this flag is True.
    """
    pipeline = await TradingPipeline.build()
    signal = make_signal(direction="long")
    bot, config, user_settings = bot_context

    state = await pipeline.run(
        signal=signal.model_dump(),
        bot=bot,
        bot_config=config,
        user_settings=user_settings,
        open_trade_count=0,
        agent_run_id="test-run-id",
        # FIX 6: Simulate orchestrator detecting injection in raw metadata
        sanitized_metadata={},
        metadata_suspicious=True,    # Injection detected before graph entry
        metadata_oversize=False,
    )

    # metadata_suspicious flag must be in state
    assert state.get("metadata_suspicious") is True
    # SecurityGuardianAgent or PromptInjectionDefenseAgent must veto
    assert state.get("veto_triggered") is True


@pytest.mark.asyncio
async def test_veto_summary_stored_as_dict(mock_repo, mock_market_data, bot_context):
    """
    FIX 4: veto_summary in state must be a plain dict (not a dataclass).
    It is serialised to DB and must be JSON-serialisable.
    """
    pipeline = await TradingPipeline.build()
    signal = make_signal(direction="long", symbol="'; DROP TABLE signals; --")
    bot, config, user_settings = bot_context

    state = await pipeline.run(
        signal=signal.model_dump(),
        bot=bot,
        bot_config=config,
        user_settings=user_settings,
        open_trade_count=0,
        agent_run_id="test-run-id",
        sanitized_metadata={},
        metadata_suspicious=False,
        metadata_oversize=False,
    )

    if state.get("veto_triggered"):
        veto_summary = state.get("veto_summary")
        assert isinstance(veto_summary, dict), (
            "veto_summary must be a plain dict (via veto_summary_to_dict()), "
            "not a VetoSummaryResult dataclass"
        )


@pytest.mark.asyncio
async def test_position_limit_reached_triggers_veto(mock_repo, mock_market_data, bot_context):
    """When open_trade_count >= max_concurrent_trades, CRO should veto."""
    pipeline = await TradingPipeline.build()
    signal = make_signal(direction="long")
    bot, config, user_settings = bot_context

    state = await pipeline.run(
        signal=signal.model_dump(),
        bot=bot,
        bot_config=config,
        user_settings=user_settings,
        open_trade_count=10,   # Way above max_concurrent_trades=3
        agent_run_id="test-run-id",
        sanitized_metadata={},
        metadata_suspicious=False,
        metadata_oversize=False,
    )

    assert state.get("veto_triggered") is True
    # FIX 4: position_limit_reached → wait (policy veto, not reject)
    veto_summary = state.get("veto_summary") or {}
    assert (
        "position_limit_reached" in veto_summary.get("all_risk_flags", [])
        or state.get("final_decision") in ("wait", "reject")
    )


@pytest.mark.asyncio
async def test_inactive_bot_triggers_veto(mock_repo, mock_market_data, bot_context):
    """A bot that is not active should be vetoed by CRO."""
    pipeline = await TradingPipeline.build()
    signal = make_signal(direction="long")
    bot, config, user_settings = bot_context
    bot["status"] = "paused"

    state = await pipeline.run(
        signal=signal.model_dump(),
        bot=bot,
        bot_config=config,
        user_settings=user_settings,
        open_trade_count=0,
        agent_run_id="test-run-id",
        sanitized_metadata={},
        metadata_suspicious=False,
        metadata_oversize=False,
    )

    assert state.get("veto_triggered") is True
