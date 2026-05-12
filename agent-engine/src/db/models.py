"""
Pydantic v2 models mirroring the Supabase database schema.
These are used for parsing DB rows and for strict inter-component contracts.

NOTE: Fields that are not consumed by the engine are omitted for brevity.
     Add columns as needed when extending agent capabilities.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, ConfigDict


# ── Enums (mirror PostgreSQL enums) ──────────────────────────────────────────

class UserRole(str, Enum):
    USER = "user"
    PRO_USER = "pro_user"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"
    SECURITY_ADMIN = "security_admin"


class BotMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"
    SHADOW = "shadow"


class BotStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"
    ARCHIVED = "archived"
    ERROR = "error"


class AgentCategory(str, Enum):
    DATA = "data"
    ANALYSIS = "analysis"
    CRITIQUE = "critique"
    RISK = "risk"
    SECURITY = "security"
    EXECUTION = "execution"
    MONITORING = "monitoring"
    POST_TRADE = "post_trade"
    SYSTEM_EVOLUTION = "system_evolution"


class AgentRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class AgentDecision(str, Enum):
    OPEN_LONG = "open_long"
    OPEN_SHORT = "open_short"
    WAIT = "wait"
    REJECT = "reject"
    MANUAL_APPROVAL_REQUIRED = "manual_approval_required"   # Exact DB enum value
    CLOSE_POSITION = "close_position"
    REDUCE_POSITION = "reduce_position"
    PAUSE_TRADING = "pause_trading"


class TradeDirection(str, Enum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


class TradeMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"
    SHADOW = "shadow"


class ApprovalStatus(str, Enum):
    PENDING = "pending"              # Awaiting human or automatic approval
    APPROVED = "approved"            # Explicitly approved
    REJECTED = "rejected"            # Explicitly rejected (including by veto)
    AUTO_APPROVED = "auto_approved"  # Pipeline approved automatically (paper/shadow, strong score)
    EXPIRED = "expired"              # Approval window elapsed


class SignalStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"   # Added by migration 0004
    PROCESSED = "processed"
    TRIGGERED = "triggered"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    FAILED = "failed"


class SeverityLevel(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReportStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    WONT_FIX = "wont_fix"


# ── Database row models ───────────────────────────────────────────────────────

class BaseDBModel(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        extra="ignore",       # Ignore unknown DB columns gracefully
    )


class Profile(BaseDBModel):
    id: str
    email: str
    role: UserRole = UserRole.USER
    is_banned: bool = False
    subscription_status: str = "trialing"
    risk_level: int = 2


class UserSettings(BaseDBModel):
    id: str
    user_id: str
    default_risk_per_trade_pct: float = 1.0
    max_daily_loss_pct: float = 5.0
    max_portfolio_risk_pct: float = 20.0
    max_open_trades: int = 5
    paper_trading_enabled: bool = True
    real_trading_enabled: bool = False
    real_trading_requires_approval: bool = True


class Bot(BaseDBModel):
    id: str
    user_id: str
    name: str
    mode: BotMode = BotMode.PAPER
    status: BotStatus = BotStatus.ACTIVE
    is_archived: bool = False
    active_config_id: Optional[str] = None
    exchange_account_id: Optional[str] = None
    requires_manual_approval: bool = False
    real_trading_enabled: bool = False   # True only when operator-approved for live
    max_open_positions: int = 3
    max_position_size_pct: float = 5.0
    risk_per_trade_pct: float = 2.0
    max_daily_loss_pct: float = 5.0
    base_currency: str = "USDT"
    trading_pairs: list[str] = Field(default_factory=list)
    # Strategy & cadence (migration 0012)
    strategy_type: Optional[str] = None  # scalping | momentum | trend_following | mean_reversion | balanced
    last_signal_at: Optional[str] = None
    next_signal_at: Optional[str] = None
    # Risk model (migration 0012)
    risk_model: str = "percentage"        # percentage | fixed_usd
    risk_value: float = 2.0               # % or USD depending on risk_model
    risk_reward_ratio: float = 2.0        # default 1R:2R
    # Warmup tracking (migration 0012)
    warmup_status: str = "pending"        # pending | warming_up | ready
    warmup_started_at: Optional[str] = None
    warmup_completed_at: Optional[str] = None
    candles_collected: int = 0
    candles_required: int = 100


class BotConfig(BaseDBModel):
    id: str
    bot_id: str
    user_id: str
    version: int = 1
    config: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class AgentDefinition(BaseDBModel):
    id: str
    name: str
    display_name: str
    agent_type: str           # DB column; Python class name to instantiate
    category: AgentCategory
    description: Optional[str] = None
    enabled: bool = True
    can_veto: bool = False
    default_weight: float = 1.0
    timeout_seconds: int = 30
    version: str = "1.0.0"

    @property
    def class_name(self) -> str:
        """Alias for agent_type — used by the agent registry for class lookup."""
        return self.agent_type


class MarketSnapshot(BaseDBModel):
    id: str
    exchange: str
    symbol: str
    timeframe: str
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float
    bid_price: Optional[float] = None
    ask_price: Optional[float] = None
    spread_pct: Optional[float] = None
    order_book_depth: Optional[dict[str, Any]] = None
    technical_indicators: dict[str, Any] = Field(default_factory=dict)
    funding_rate: Optional[float] = None
    open_interest: Optional[float] = None
    captured_at: str
    source: Optional[str] = None
    created_at: Optional[str] = None


class Signal(BaseDBModel):
    id: str
    user_id: str
    bot_id: str
    agent_run_id: Optional[str] = None
    market_snapshot_id: Optional[str] = None
    exchange: str
    symbol: str
    direction: TradeDirection
    signal_type: str
    confidence: Optional[float] = None
    score: Optional[float] = None
    status: SignalStatus = SignalStatus.PENDING
    processing_started_at: Optional[str] = None
    processing_worker_id: Optional[str] = None
    processed_at: Optional[str] = None        # Set when status → 'processed'
    retry_count: int = 0                       # Incremented by release_stuck_signals
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class ExchangeAccount(BaseDBModel):
    id: str
    user_id: str
    exchange_name: str
    account_label: str
    connection_status: str
    can_read: bool = False
    can_trade: bool = False
    can_withdraw: bool = False
    withdrawal_detected: bool = False
    is_active: bool = True
    testnet: bool = False


# ── Agent Output (canonical format for every agent) ──────────────────────────

class AgentOutputResult(BaseModel):
    """
    Strictly typed output from every agent.
    Stored in agent_outputs.output JSONB column.
    """
    agent_name: str
    agent_definition_id: str
    agent_category: AgentCategory
    decision: AgentDecision
    score: float = Field(..., ge=-100.0, le=100.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    veto: bool = False
    reasoning: str
    output: dict[str, Any] = Field(default_factory=dict)
    risk_flags: list[str] = Field(default_factory=list)
    security_flags: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    duration_ms: Optional[int] = None
    error: Optional[str] = None

    @field_validator("score")
    @classmethod
    def clamp_score(cls, v: float) -> float:
        return max(-100.0, min(100.0, v))

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


# ── Aggregated result models ──────────────────────────────────────────────────

class VetoSummary(BaseModel):
    triggered: bool = False
    vetoing_agents: list[str] = Field(default_factory=list)
    veto_reasons: list[str] = Field(default_factory=list)
    severity: SeverityLevel = SeverityLevel.INFO


class ScoreSummary(BaseModel):
    raw_score: float
    weighted_score: float
    confidence_adjusted_score: float
    final_score: float
    risk_penalty: float = 0.0
    security_penalty: float = 0.0
    data_quality_penalty: float = 0.0
    manipulation_penalty: float = 0.0
    agent_scores: dict[str, float] = Field(default_factory=dict)
    agent_weights: dict[str, float] = Field(default_factory=dict)


class RiskSummary(BaseModel):
    overall_risk_level: SeverityLevel = SeverityLevel.LOW
    flags: list[str] = Field(default_factory=list)
    position_size_ok: bool = True
    daily_loss_ok: bool = True
    max_positions_ok: bool = True
    risk_penalty: float = 0.0


class SecuritySummary(BaseModel):
    overall_security_level: SeverityLevel = SeverityLevel.LOW
    flags: list[str] = Field(default_factory=list)
    injection_detected: bool = False
    suspicious_conditions: list[str] = Field(default_factory=list)
    security_penalty: float = 0.0


# ── Write models (used when inserting into DB) ────────────────────────────────

class AgentRunInsert(BaseModel):
    user_id: str
    bot_id: str
    run_status: str = "running"
    trigger_type: str = "signal"
    started_at: str
    input_snapshot: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentOutputInsert(BaseModel):
    agent_run_id: str
    agent_definition_id: str
    user_id: str
    bot_id: str
    decision: str
    score: Optional[float]
    confidence: Optional[float]
    veto: bool
    reasoning: Optional[str]
    output: dict[str, Any]
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: Optional[int] = None


class TradeDecisionInsert(BaseModel):
    user_id: str
    bot_id: str
    agent_run_id: str
    signal_id: str
    exchange: str
    symbol: str
    direction: str
    mode: str
    final_decision: str
    score_summary: dict[str, Any]
    risk_summary: dict[str, Any]
    security_summary: dict[str, Any]
    veto_summary: dict[str, Any]
    agent_outputs_snapshot: dict[str, Any]
    approval_status: str
    manual_approval_required: bool
    metadata: dict[str, Any] = Field(default_factory=dict)
    execution_status: str = "pending_execution"
    execution_worker_id: Optional[str] = None
    execution_started_at: Optional[str] = None
    execution_completed_at: Optional[str] = None
    execution_error: Optional[str] = None
    execution_retry_count: int = 0
    linked_trade_id: Optional[str] = None


class RiskLogInsert(BaseModel):
    user_id: str
    bot_id: Optional[str] = None
    trade_decision_id: Optional[str] = None
    trade_id: Optional[str] = None
    agent_run_id: Optional[str] = None
    risk_type: str
    severity: str
    triggered: bool = False
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SecurityLogInsert(BaseModel):
    user_id: Optional[str] = None
    event_type: str
    severity: str
    source: str = "agent_engine"
    ip_address: Optional[str] = None
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditLogInsert(BaseModel):
    user_id: Optional[str] = None
    actor_role: Optional[str] = None
    action: str
    table_name: Optional[str] = None
    record_id: Optional[str] = None
    old_values: Optional[dict[str, Any]] = None
    new_values: Optional[dict[str, Any]] = None
    source: str = "agent_engine"
    metadata: dict[str, Any] = Field(default_factory=dict)


class SystemEvolutionReportInsert(BaseModel):
    generated_by_agent: Optional[str] = None
    agent_run_id: Optional[str] = None
    finding_type: str
    description: str
    recommended_new_agents: list[dict[str, Any]] = Field(default_factory=list)
    recommended_schema_changes: list[dict[str, Any]] = Field(default_factory=list)
    recommended_risk_changes: list[dict[str, Any]] = Field(default_factory=list)
    priority: int = Field(default=3, ge=1, le=5)
    status: str = "open"
    metadata: dict[str, Any] = Field(default_factory=dict)
