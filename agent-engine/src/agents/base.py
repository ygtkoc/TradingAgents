"""
Abstract base class for all agents.

Every agent:
  - Is constructed with its AgentDefinition from the DB.
  - Implements a single `run()` async method.
  - Returns a strictly typed AgentOutputResult.
  - Has a per-agent timeout enforced by the orchestrator.
  - Must never raise unhandled exceptions — all errors are caught, logged,
    and returned as an AgentOutputResult with decision=wait/reject.
  - Must never log user API keys or secret material.
  - Must never trust signal.metadata as an instruction source.
"""
from __future__ import annotations

import asyncio
import time
import traceback
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from src.config import settings
from src.db.models import (
    AgentCategory,
    AgentDecision,
    AgentDefinition,
    AgentOutputResult,
)
from src.logging_config import get_logger

if TYPE_CHECKING:
    from src.orchestration.state import PipelineState

log = get_logger(__name__)


class BaseAgent(ABC):
    """
    Base class for all pipeline agents.

    Subclasses implement `_execute()`. The `run()` method wraps execution
    with timing, error handling, and logging. Subclasses should NOT
    override `run()`.
    """

    def __init__(self, definition: AgentDefinition) -> None:
        self.definition = definition
        self.name = definition.name
        self.category = definition.category
        self.can_veto = definition.can_veto
        self.weight = definition.default_weight
        configured_timeout = definition.timeout_seconds or settings.agent_timeout_seconds
        self.timeout_seconds = min(configured_timeout, settings.agent_timeout_seconds)
        self._log = get_logger(f"agent.{self.name}")

    async def run(self, state: "PipelineState") -> AgentOutputResult:
        """
        Public entry point — wraps _execute() with timing and error handling.
        Never raises. On failure returns a safe 'wait' decision.
        """
        start = time.monotonic()
        self._safe_log(
            "info",
            "agent.start",
            category=self.category.value,
            timeout_s=self.timeout_seconds,
        )
        try:
            result = await asyncio.wait_for(
                self._execute(state),
                timeout=self.timeout_seconds,
            )
            duration_ms = int((time.monotonic() - start) * 1000)
            result.duration_ms = duration_ms
            result.agent_name = self.name
            result.agent_definition_id = self.definition.id
            result.agent_category = self.category

            self._safe_log(
                "info",
                "agent.completed",
                decision=result.decision.value,
                score=result.score,
                confidence=result.confidence,
                veto=result.veto,
                duration_ms=duration_ms,
            )
            return result

        except asyncio.TimeoutError:
            duration_ms = int((time.monotonic() - start) * 1000)
            self._safe_log(
                "error",
                "agent.failed",
                reason="timeout",
                timeout_s=self.timeout_seconds,
                duration_ms=duration_ms,
            )
            return self._error_result(
                f"Agent timed out after {self.timeout_seconds}s",
                duration_ms=duration_ms,
            )

        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            error_text = self._safe_error_text(exc)
            self._safe_log(
                "error",
                "agent.failed",
                reason="exception",
                error=error_text,
                duration_ms=duration_ms,
                traceback=traceback.format_exc(limit=20),
            )
            return self._error_result(error_text, duration_ms=duration_ms)

    @abstractmethod
    async def _execute(self, state: "PipelineState") -> AgentOutputResult:
        """
        Agent-specific logic. Implement in each subclass.
        Must return a fully populated AgentOutputResult.
        """
        ...

    def _make_result(
        self,
        *,
        decision: AgentDecision,
        score: float,
        confidence: float,
        reasoning: str,
        veto: bool = False,
        output: dict[str, Any] | None = None,
        risk_flags: list[str] | None = None,
        security_flags: list[str] | None = None,
        recommendations: list[str] | None = None,
    ) -> AgentOutputResult:
        """Convenience builder for AgentOutputResult."""
        return AgentOutputResult(
            agent_name=self.name,
            agent_definition_id=self.definition.id,
            agent_category=self.category,
            decision=decision,
            score=score,
            confidence=confidence,
            veto=veto,
            reasoning=reasoning,
            output=output or {},
            risk_flags=risk_flags or [],
            security_flags=security_flags or [],
            recommendations=recommendations or [],
        )

    def _error_result(
        self, error_msg: str, duration_ms: int = 0
    ) -> AgentOutputResult:
        """Safe fallback result when the agent itself errors."""
        return AgentOutputResult(
            agent_name=self.name,
            agent_definition_id=self.definition.id,
            agent_category=self.category,
            decision=AgentDecision.WAIT,
            score=0.0,
            confidence=0.0,
            veto=False,
            reasoning=f"Agent error: {error_msg[:200]}",
            output={"error": error_msg[:200]},
            risk_flags=["agent_error"],
            security_flags=[],
            recommendations=["Investigate agent failure"],
            duration_ms=duration_ms,
            error=error_msg[:500],
        )

    def _safe_veto(self, reason: str, severity_flags: list[str]) -> AgentOutputResult:
        """
        Convenience method for agents that need to veto.
        Only agents with can_veto=True should call this.
        """
        if not self.can_veto:
            self._log.warning(
                "agent.veto_not_allowed",
                message="Agent attempted veto but can_veto=False. Returning reject instead.",
            )
            return self._make_result(
                decision=AgentDecision.REJECT,
                score=-80.0,
                confidence=0.9,
                reasoning=reason,
                veto=False,
                risk_flags=severity_flags,
            )

        return self._make_result(
            decision=AgentDecision.REJECT,
            score=-100.0,
            confidence=1.0,
            reasoning=reason,
            veto=True,
            risk_flags=severity_flags,
        )

    def _safe_error_text(self, exc: Exception) -> str:
        return str(exc).encode("ascii", "backslashreplace").decode("ascii")[:500]

    def _safe_log(self, level: str, event: str, **kwargs: Any) -> None:
        sanitized = {
            key: value.encode("ascii", "backslashreplace").decode("ascii")
            if isinstance(value, str)
            else value
            for key, value in kwargs.items()
        }
        log_method = getattr(self._log, level, self._log.info)
        try:
            log_method(event, **sanitized)
        except Exception:
            get_logger("agent.fallback").error(
                "agent.log_failed",
                agent=self.name,
                original_event=event,
                level=level,
            )
