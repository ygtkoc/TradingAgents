"""
Pydantic v2 models mirroring the Supabase database schema for the Execution Engine.

Design rules:
  - ConfigDict(extra="ignore") everywhere: DB columns the engine doesn't use
    do not cause parse failures.
  - All models use str for UUIDs (avoids UUID import friction with supabase-py).
  - Insert models (.*Insert) only contain writable fields.
  - Read models contain the full row structure.
  - NEVER store or log decrypted API keys anywhere in these models.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Enums ─────────────────────────────────────────────────────────────────────

class ExecutionStatus(str, Enum):
    PENDING_EXECUTION = "pending_execution"
    EXECUTING         = "executing"
    EXECUTED          = "executed"
    FAILED            = "failed"
    SKIPPED           = "skipped"


class TradeSide(str, Enum):
    BUY  = "buy"
    SELL = "sell"


class TradeMode(str, Enum):
    PAPER  = "paper"
    LIVE   = "live"
    SHADOW = "shadow"


class TradeStatus(str, Enum):
    OPEN      = "open"
    CLOSED    = "closed"
    CANCELLED = "cancelled"
    FAILED    = "failed"
    SIMULATED = "simulated"
    PENDING   = "pending"


class TradeDirection(str, Enum):
    LONG    = "long"
    SHORT   = "short"
    NEUTRAL = "neutral"


class BotMode(str, Enum):
    PAPER  = "paper"
    LIVE   = "live"
    SHADOW = "shadow"


class BotStatus(str, Enum):
    DRAFT    = "draft"
    ACTIVE   = "active"
    PAUSED   = "paused"
    STOPPED  = "stopped"
    ARCHIVED = "archived"
    ERROR    = "error"


class SeverityLevel(str, Enum):
    INFO     = "info"
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


# ── Read Models (DB rows → Python) ────────────────────────────────────────────

class TradeDecision(BaseModel):
    """Full trade_decision row including execution columns added by migration 0005."""
    model_config = ConfigDict(extra="ignore")

    id:                       str
    user_id:                  str
    bot_id:                   str
    agent_run_id:             Optional[str] = None
    signal_id:                Optional[str] = None
    exchange:                 str
    symbol:                   str
    direction:                str
    mode:                     str                          # paper / live / shadow
    final_decision:           str                          # open_long / open_short
    approval_status:          str                          # approved / auto_approved
    manual_approval_required: bool = False
    score_summary:            dict[str, Any] = Field(default_factory=dict)
    risk_summary:             dict[str, Any] = Field(default_factory=dict)
    security_summary:         dict[str, Any] = Field(default_factory=dict)
    veto_summary:             dict[str, Any] = Field(default_factory=dict)
    agent_outputs_snapshot:   dict[str, Any] = Field(default_factory=dict)
    metadata:                 dict[str, Any] = Field(default_factory=dict)

    # Execution columns (from migration 0005)
    execution_status:         str = ExecutionStatus.PENDING_EXECUTION.value
    execution_worker_id:      Optional[str] = None
    execution_started_at:     Optional[str] = None
    execution_completed_at:   Optional[str] = None
    execution_error:          Optional[str] = None
    execution_retry_count:    int = 0
    linked_trade_id:          Optional[str] = None

    created_at:               str
    updated_at:               Optional[str] = None


class Bot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id:                       str
    user_id:                  str
    name:                     str
    status:                   str
    mode:                     str
    real_trading_enabled:     bool = False
    requires_manual_approval: bool = False
    max_open_positions:       int = 3
    max_position_size_pct:    float = 5.0
    risk_per_trade_pct:       float = 1.0
    max_daily_loss_pct:       float = 5.0
    base_currency:            str = "USDT"
    trading_pairs:            list[str] = Field(default_factory=list)
    active_config_id:         Optional[str] = None
    exchange_account_id:      Optional[str] = None
    is_archived:              bool = False


class BotConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id:       str
    bot_id:   str
    user_id:  str
    version:  int
    config:   dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class UserSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    user_id:                       str
    trading_enabled:               bool = True
    real_trading_enabled:          bool = False
    real_trading_requires_approval: bool = True
    real_trading_allowed:          bool = False   # subscription-level gate
    max_concurrent_trades:         Optional[int] = None
    daily_loss_limit_usd:          Optional[float] = None


class ExchangeAccount(BaseModel):
    """
    Exchange account record.

    SECURITY NOTE: encrypted_api_key, encrypted_api_secret, and key_iv fields
    contain ciphertext and are safe to read. Decryption happens exclusively
    in KeyProvider; the plaintext is NEVER stored in this model.
    """
    model_config = ConfigDict(extra="ignore")

    id:                  str
    user_id:             str
    bot_id:              Optional[str] = None
    exchange:            str
    label:               Optional[str] = None
    is_active:           bool = False
    can_trade:           bool = False
    can_withdraw:        bool = True    # Default True = unsafe until verified False
    withdrawal_detected: bool = False
    # Ciphertext fields (not plaintext — decrypted only in KeyProvider)
    encrypted_api_key:    Optional[str] = None
    encrypted_api_secret: Optional[str] = None
    key_iv:               Optional[str] = None
    metadata:             dict[str, Any] = Field(default_factory=dict)


class MarketSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id:          str
    exchange:    str
    symbol:      str
    timeframe:   str = "1h"
    close_price: float
    high_price:  float
    low_price:   float
    open_price:  float
    volume:      float
    spread_pct:  Optional[float] = None
    captured_at: str


class Trade(BaseModel):
    """Full trade row as read from DB."""
    model_config = ConfigDict(extra="ignore")

    id:                 str
    user_id:            str
    bot_id:             str
    trade_decision_id:  Optional[str] = None
    agent_run_id:       Optional[str] = None
    exchange:           str
    symbol:             str
    side:               str
    direction:          str
    mode:               str
    status:             str
    lifecycle_status:   Optional[str] = None
    entry_price:        float
    quantity:           float
    stop_loss:          Optional[float] = None
    take_profit:        Optional[float] = None
    exit_price:         Optional[float] = None
    closed_at:          Optional[str] = None
    pnl:                Optional[float] = None
    exchange_order_id:  Optional[str] = None
    filled_quantity:    Optional[float] = None
    avg_fill_price:     Optional[float] = None
    metadata:           dict[str, Any] = Field(default_factory=dict)
    created_at:         str
    updated_at:         Optional[str] = None


class PlatformSettings(BaseModel):
    """
    Parsed view of the platform_settings table.
    Defaults match the seed values from migration 0006.
    """
    model_config = ConfigDict(extra="ignore")

    global_trading_enabled:   bool  = True
    live_execution_enabled:   bool  = False
    emergency_close_enabled:  bool  = True
    max_allowed_slippage_pct: float = 1.0

    @classmethod
    def from_rows(cls, rows: list[dict]) -> "PlatformSettings":
        """Build from list of {key, value} dicts (as returned by the DB query)."""
        mapping: dict = {}
        for row in rows:
            key = row.get("key", "")
            val = row.get("value")
            if key == "global_trading_enabled":
                mapping["global_trading_enabled"] = bool(val)
            elif key == "live_execution_enabled":
                mapping["live_execution_enabled"] = bool(val)
            elif key == "emergency_close_enabled":
                mapping["emergency_close_enabled"] = bool(val)
            elif key == "max_allowed_slippage_pct":
                try:
                    mapping["max_allowed_slippage_pct"] = float(val)
                except (TypeError, ValueError):
                    pass
        return cls(**mapping)


# ── Insert Models (Python → DB) ───────────────────────────────────────────────

class TradeInsert(BaseModel):
    user_id:            str
    bot_id:             str
    trade_decision_id:  Optional[str] = None
    agent_run_id:       Optional[str] = None
    exchange:           str
    symbol:             str
    side:               str
    direction:          str
    mode:               str
    status:             str = TradeStatus.OPEN.value
    lifecycle_status:   Optional[str] = None
    entry_price:        float
    quantity:           float
    stop_loss:          Optional[float] = None
    take_profit:        Optional[float] = None
    exchange_order_id:  Optional[str] = None
    filled_quantity:    Optional[float] = None
    avg_fill_price:     Optional[float] = None
    metadata:           dict[str, Any] = Field(default_factory=dict)


class TradeEventInsert(BaseModel):
    trade_id:           Optional[str] = None
    trade_decision_id:  Optional[str] = None
    bot_id:             Optional[str] = None
    user_id:            Optional[str] = None
    event_type:         str
    details:            dict[str, Any] = Field(default_factory=dict)


class RiskLogInsert(BaseModel):
    user_id:            Optional[str] = None
    bot_id:             Optional[str] = None
    trade_decision_id:  Optional[str] = None
    trade_id:           Optional[str] = None
    risk_type:          str
    severity:           str = SeverityLevel.MEDIUM.value
    triggered:          bool = False
    message:            str
    metadata:           dict[str, Any] = Field(default_factory=dict)


class SecurityLogInsert(BaseModel):
    user_id:     Optional[str] = None
    event_type:  str
    severity:    str = SeverityLevel.MEDIUM.value
    source:      str = "execution_engine"
    message:     str
    metadata:    dict[str, Any] = Field(default_factory=dict)


class AuditLogInsert(BaseModel):
    user_id:    Optional[str] = None
    action:     str
    record_id:  Optional[str] = None
    table_name: Optional[str] = None
    source:     str = "execution_engine"
    metadata:   dict[str, Any] = Field(default_factory=dict)
