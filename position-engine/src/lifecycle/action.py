"""
LifecycleAction — the result type returned by every lifecycle check module.

Priority ordering (highest wins when multiple triggers fire simultaneously):
  1. CLOSE_EMERGENCY         — kill switch / security halt
  2. CLOSE_STOP_LOSS         — stop-loss triggered
  3. CLOSE_TAKE_PROFIT       — take-profit triggered
  4. CLOSE_TRAILING_STOP     — trailing stop triggered
  5. MARK_NEEDS_RECONCILIATION
  6. PAUSE_MONITORING
  7. UPDATE_TRAILING_STOP    — update price but don't close
  8. UPDATE_PNL              — just recalculate unrealized P&L
  9. HOLD                    — nothing to do
  10. ERROR                  — internal error (lowest — error path)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional


class ActionType(IntEnum):
    """
    Lifecycle action type with embedded priority.
    Higher int = higher priority.
    """
    ERROR                    = 0
    HOLD                     = 1
    UPDATE_PNL               = 2
    UPDATE_TRAILING_STOP     = 3
    PAUSE_MONITORING         = 4
    MARK_NEEDS_RECONCILIATION = 5
    CLOSE_TRAILING_STOP      = 6
    CLOSE_TAKE_PROFIT        = 7
    CLOSE_STOP_LOSS          = 8
    CLOSE_EMERGENCY          = 9


@dataclass
class LifecycleAction:
    """
    Returned by lifecycle check functions.

    Callers should compare action.priority and keep the highest-priority one.
    """
    action_type:     ActionType
    reason:          str
    metadata:        dict[str, Any]   = field(default_factory=dict)
    close_price:     Optional[float]  = None   # price at which to close (if closing)
    new_trailing_stop: Optional[float] = None  # updated trailing stop price
    new_highest_seen:  Optional[float] = None  # updated highest price for longs
    new_lowest_seen:   Optional[float] = None  # updated lowest price for shorts
    unrealized_pnl:    Optional[float] = None  # computed P&L for UPDATE_PNL

    @property
    def is_close_action(self) -> bool:
        return self.action_type in (
            ActionType.CLOSE_STOP_LOSS,
            ActionType.CLOSE_TAKE_PROFIT,
            ActionType.CLOSE_TRAILING_STOP,
            ActionType.CLOSE_EMERGENCY,
        )

    @property
    def priority(self) -> int:
        return int(self.action_type)


def hold() -> LifecycleAction:
    return LifecycleAction(action_type=ActionType.HOLD, reason="no trigger")


def update_pnl(pnl: float) -> LifecycleAction:
    return LifecycleAction(
        action_type=ActionType.UPDATE_PNL,
        reason="periodic P&L update",
        unrealized_pnl=pnl,
    )


def highest_priority(actions: list[LifecycleAction]) -> LifecycleAction:
    """Return the action with the highest priority from a list."""
    if not actions:
        return hold()
    return max(actions, key=lambda a: a.priority)
