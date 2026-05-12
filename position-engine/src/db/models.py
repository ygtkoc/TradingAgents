"""
Pydantic v2 models for the Position Engine.

Includes all lifecycle columns added by migration 0006.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Enums ─────────────────────────────────────────────────────────────────────

class LifecycleStatus(str, Enum):
    IDLE                 = "idle"
    MONITORING           = "monitoring"
    CLOSING              = "closing"
    CLOSED               = "closed"
    FAILED               = "failed"
    NEEDS_RECONCILIATION = "needs_reconciliation"


class TradeStatus(str, Enum):
    OPEN      = "open"
    CLOSED    = "closed"
    CANCELLED = "cancelled"
    FAILED    = "failed"
    SIMULATED = "simulated"
    PENDING   = "pending"


class TradeMode(str, Enum):
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


# ── Read Models ───────────────────────────────────────────────────────────────

class Trade(BaseModel):
    """Full trade row including all lifecycle columns from migration 0006."""
    model_config = ConfigDict(extra="ignore")

    id:                       str
    user_id:                  str
    bot_id:                   str
    trade_decision_id:        Optional[str]  = None
    agent_run_id:             Optional[str]  = None
    exchange:                 str
    symbol:                   str
    side:                     str            # buy / sell
    direction:                str            # long / short / neutral
    mode:                     str            # paper / live / shadow
    status:                   str            # open / closed / …
    entry_price:              float
    quantity:                 float
    stop_loss:                Optional[float] = None
    take_profit:              Optional[float] = None
    exit_price:               Optional[float] = None
    closed_at:                Optional[str]  = None
    pnl:                      Optional[float] = None
    exchange_order_id:        Optional[str]  = None
    filled_quantity:          Optional[float] = None
    avg_fill_price:           Optional[float] = None
    metadata:                 dict[str, Any] = Field(default_factory=dict)
    created_at:               str
    updated_at:               Optional[str]  = None

    # Lifecycle columns (migration 0006)
    lifecycle_status:         str   = LifecycleStatus.IDLE.value
    lifecycle_worker_id:      Optional[str]   = None
    lifecycle_claimed_at:     Optional[str]   = None
    lifecycle_last_checked_at: Optional[str]  = None
    lifecycle_error:          Optional[str]   = None
    lifecycle_retry_count:    int             = 0
    trailing_stop_price:      Optional[float] = None
    highest_price_seen:       Optional[float] = None
    lowest_price_seen:        Optional[float] = None
    close_reason:             Optional[str]   = None
    close_order_id:           Optional[str]   = None
    unrealized_pnl:           Optional[float] = None
    realized_pnl:             Optional[float] = None
    avg_exit_price:           Optional[float] = None

    @property
    def effective_quantity(self) -> float:
        return self.filled_quantity or self.quantity

    @property
    def effective_entry_price(self) -> float:
        return self.avg_fill_price or self.entry_price

    @property
    def is_long(self) -> bool:
        return self.direction == "long"

    @property
    def is_live(self) -> bool:
        return self.mode == "live"


class Bot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id:                       str
    user_id:                  str
    name:                     str
    status:                   str
    mode:                     str
    real_trading_enabled:     bool  = False
    requires_manual_approval: bool  = False
    max_open_positions:       int   = 3
    max_position_size_pct:    float = 5.0
    risk_per_trade_pct:       float = 1.0
    max_daily_loss_pct:       float = 5.0
    base_currency:            str   = "USDT"
    trading_pairs:            list[str] = Field(default_factory=list)
    exchange_account_id:      Optional[str] = None
    is_archived:              bool  = False

    # Trailing stop configuration (stored in bot config or metadata)
    trailing_stop_pct:        Optional[float] = None


class UserSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    user_id:                       str
    trading_enabled:               bool  = True
    real_trading_enabled:          bool  = False
    real_trading_allowed:          bool  = False
    real_trading_requires_approval: bool = True
    max_concurrent_trades:         Optional[int]   = None
    daily_loss_limit_usd:          Optional[float] = None


class ExchangeAccount(BaseModel):
    """
    Exchange account with encrypted API credentials.
    NEVER store plaintext keys here — decryption happens only in KeyProvider.
    """
    model_config = ConfigDict(extra="ignore")

    id:                   str
    user_id:              str
    bot_id:               Optional[str]  = None
    exchange:             str
    label:                Optional[str]  = None
    is_active:            bool  = False
    can_trade:            bool  = False
    can_withdraw:         bool  = True    # default True = unsafe until verified
    withdrawal_detected:  bool  = False
    encrypted_api_key:    Optional[str]  = None
    encrypted_api_secret: Optional[str]  = None
    key_iv:               Optional[str]  = None
    metadata:             dict[str, Any] = Field(default_factory=dict)


class MarketSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id:          str
    exchange:    str
    symbol:      str
    timeframe:   str   = "1h"
    close_price: float
    high_price:  float
    low_price:   float
    open_price:  float
    volume:      float
    spread_pct:  Optional[float] = None
    captured_at: str


class PlatformSettings(BaseModel):
    """Parsed platform_settings loaded from DB."""
    model_config = ConfigDict(extra="ignore")

    global_trading_enabled:   bool  = True
    live_execution_enabled:   bool  = False
    emergency_close_enabled:  bool  = True
    max_allowed_slippage_pct: float = 1.0

    @classmethod
    def from_rows(cls, rows: list[dict]) -> "PlatformSettings":
        """Build from a list of {key, value} rows."""
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


# ── Insert Models ─────────────────────────────────────────────────────────────

class TradeUpdateLifecycle(BaseModel):
    """Fields written back to trades during a lifecycle update."""
    lifecycle_status:          Optional[str]   = None
    lifecycle_worker_id:       Optional[str]   = None
    lifecycle_claimed_at:      Optional[str]   = None
    lifecycle_last_checked_at: Optional[str]   = None
    lifecycle_error:           Optional[str]   = None
    lifecycle_retry_count:     Optional[int]   = None
    trailing_stop_price:       Optional[float] = None
    highest_price_seen:        Optional[float] = None
    lowest_price_seen:         Optional[float] = None
    close_reason:              Optional[str]   = None
    close_order_id:            Optional[str]   = None
    unrealized_pnl:            Optional[float] = None
    realized_pnl:              Optional[float] = None
    exit_price:                Optional[float] = None
    avg_exit_price:            Optional[float] = None
    status:                    Optional[str]   = None
    closed_at:                 Optional[str]   = None
    pnl:                       Optional[float] = None
    filled_quantity:           Optional[float] = None  # reconciliation partial-fill update

    def to_db_dict(self) -> dict:
        """Return only non-None fields for the DB update."""
        return {k: v for k, v in self.model_dump().items() if v is not None}


class TradeEventInsert(BaseModel):
    trade_id:          Optional[str]   = None
    trade_decision_id: Optional[str]   = None
    bot_id:            Optional[str]   = None
    user_id:           Optional[str]   = None
    event_type:        str
    details:           dict[str, Any]  = Field(default_factory=dict)


class RiskLogInsert(BaseModel):
    user_id:           Optional[str]  = None
    bot_id:            Optional[str]  = None
    trade_decision_id: Optional[str]  = None
    trade_id:          Optional[str]  = None
    risk_type:         str
    severity:          str            = SeverityLevel.MEDIUM.value
    triggered:         bool           = False
    message:           str
    metadata:          dict[str, Any] = Field(default_factory=dict)


class SecurityLogInsert(BaseModel):
    user_id:    Optional[str]  = None
    event_type: str
    severity:   str            = SeverityLevel.HIGH.value
    source:     str            = "position_engine"
    message:    str
    metadata:   dict[str, Any] = Field(default_factory=dict)


class AuditLogInsert(BaseModel):
    user_id:    Optional[str]  = None
    action:     str
    record_id:  Optional[str]  = None
    table_name: Optional[str]  = None
    source:     str            = "position_engine"
    metadata:   dict[str, Any] = Field(default_factory=dict)
