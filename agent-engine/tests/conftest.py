"""
pytest configuration and shared fixtures for the agent engine test suite.

All fixtures that touch the database use a mock/stub approach —
the real Supabase client is never called in unit tests.
Integration tests (marked with @pytest.mark.integration) require
a live Supabase connection and are excluded from CI by default.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db.models import (
    AgentCategory,
    AgentDecision,
    AgentDefinition,
    BotMode,
    BotStatus,
    MarketSnapshot,
    Signal,
    SignalStatus,
    TradeDirection,
)


# ── Time helpers ──────────────────────────────────────────────────────────────

def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Model factories ───────────────────────────────────────────────────────────

def make_signal(
    symbol: str = "BTC/USDT",
    exchange: str = "binance",
    direction: str = "long",
    bot_id: str | None = None,
    user_id: str | None = None,
    metadata: dict | None = None,
) -> Signal:
    return Signal(
        id=str(uuid.uuid4()),
        user_id=user_id or str(uuid.uuid4()),
        bot_id=bot_id or str(uuid.uuid4()),
        symbol=symbol,
        exchange=exchange,
        direction=TradeDirection(direction),
        signal_type="technical",
        status=SignalStatus.PROCESSING,
        metadata=metadata or {},
        created_at=utcnow().isoformat(),
    )


def make_snapshot(
    symbol: str = "BTC/USDT",
    exchange: str = "binance",
    close_price: float = 50000.0,
    high_price: float = 51000.0,
    low_price: float = 49000.0,
    open_price: float = 50000.0,
    volume: float = 1000.0,
    spread_pct: float = 0.1,
    captured_at: datetime | None = None,
) -> MarketSnapshot:
    return MarketSnapshot(
        id=str(uuid.uuid4()),
        exchange=exchange,
        symbol=symbol,
        timeframe="1h",
        close_price=close_price,
        high_price=high_price,
        low_price=low_price,
        open_price=open_price,
        volume=volume,
        spread_pct=spread_pct,
        captured_at=(captured_at or utcnow()).isoformat(),
        technical_indicators={},
    )


def make_agent_definition(
    name: str = "test_agent",
    category: AgentCategory = AgentCategory.ANALYSIS,
    can_veto: bool = False,
    default_weight: float = 1.0,
    class_name: str = "TechnicalAnalysisAgent",
) -> AgentDefinition:
    return AgentDefinition(
        id=str(uuid.uuid4()),
        name=name,
        display_name=name.replace("_", " ").title(),
        agent_type=class_name,   # DB column; .class_name property returns this
        category=category,
        can_veto=can_veto,
        default_weight=default_weight,
        timeout_seconds=30,
        enabled=True,
    )


def make_snapshots_series(
    n: int = 50,
    base_price: float = 50000.0,
    trend: float = 0.0,  # per-bar change in price
    volume: float = 1000.0,
) -> list[MarketSnapshot]:
    """Creates n synthetic snapshots in chronological order (newest first from DB)."""
    snapshots = []
    for i in range(n):
        price = base_price + i * trend
        snapshots.append(
            make_snapshot(
                close_price=price,
                high_price=price * 1.01,
                low_price=price * 0.99,
                open_price=price,
                volume=volume,
            )
        )
    # Return newest first (as DB would)
    return list(reversed(snapshots))


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def long_signal():
    return make_signal(direction="long")


@pytest.fixture
def short_signal():
    return make_signal(direction="short")


@pytest.fixture
def btc_snapshots():
    """50 synthetic BTC snapshots in a mild uptrend."""
    return make_snapshots_series(n=50, base_price=50000.0, trend=10.0)


@pytest.fixture
def flat_snapshots():
    """50 synthetic snapshots with no trend."""
    return make_snapshots_series(n=50, base_price=50000.0, trend=0.0)


@pytest.fixture
def pipeline_state_long(long_signal, btc_snapshots):
    """Minimal pipeline state for a long signal with BTC data."""
    return {
        "signal": long_signal.model_dump(),
        "market_snapshot": btc_snapshots[0].model_dump(),
        "price_history": [s.model_dump() for s in btc_snapshots],
        "agent_results": [],
        "manipulation_flags": [],
        "manipulation_score_penalty": 0.0,
        "data_quality_score": 100.0,
        "data_quality_penalty": 0.0,
        "risk_score": 80.0,
        "veto_triggered": False,
        "veto_agent_name": None,
        "open_trade_count": 0,
    }


@pytest.fixture
def tech_analysis_agent():
    """TechnicalAnalysisAgent instance with a mock definition."""
    from src.agents.analysis import TechnicalAnalysisAgent
    defn = make_agent_definition(
        name="technical_analysis_agent",
        category=AgentCategory.ANALYSIS,
        class_name="TechnicalAnalysisAgent",
    )
    return TechnicalAnalysisAgent(defn)


@pytest.fixture
def risk_auditor_agent():
    from src.agents.risk import RiskAuditorAgent
    defn = make_agent_definition(
        name="risk_auditor_agent",
        category=AgentCategory.RISK,
        can_veto=True,
        class_name="RiskAuditorAgent",
    )
    return RiskAuditorAgent(defn)
