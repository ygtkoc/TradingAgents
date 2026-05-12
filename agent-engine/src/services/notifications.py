"""
Notification helpers for post-pipeline events.

Currently a stub — extend with real notification channels
(email, Slack, Telegram, push) as needed.

Notifications are fire-and-forget: failures are logged but never
propagate to the main pipeline. A notification failure must never
block or fail a trade decision.
"""
from __future__ import annotations

from typing import Any, Optional

from src.logging_config import get_logger

log = get_logger(__name__)


async def notify_trade_decision(
    user_id: str,
    bot_id: str,
    symbol: str,
    decision: str,
    score: float,
    reasoning: str,
    decision_id: Optional[str] = None,
    dry_run: bool = False,
) -> None:
    """
    Fires a notification to the user about a new trade decision.

    Currently logs only. Wire up real delivery here.
    """
    try:
        log.info(
            "notification.trade_decision",
            user_id=user_id,
            bot_id=bot_id,
            symbol=symbol,
            decision=decision,
            score=round(score, 2),
            decision_id=decision_id,
            dry_run=dry_run,
        )
        # TODO: implement real notification delivery
        # e.g. insert into user_notifications table, trigger Edge Function webhook
    except Exception as exc:
        # Non-blocking: log and swallow
        log.error("notification.failed", error=str(exc)[:200])


async def notify_veto(
    user_id: str,
    bot_id: str,
    symbol: str,
    veto_agent: str,
    reason: str,
    flags: list[str],
) -> None:
    """Notifies the user when a veto blocks a trade."""
    try:
        log.warning(
            "notification.veto",
            user_id=user_id,
            bot_id=bot_id,
            symbol=symbol,
            veto_agent=veto_agent,
            reason=reason[:200],
            flags=flags,
        )
        # TODO: deliver veto alert to user dashboard
    except Exception as exc:
        log.error("notification.veto_failed", error=str(exc)[:200])


async def notify_pipeline_error(
    signal_id: str,
    error: str,
    worker_id: str,
) -> None:
    """Notifies admins of a pipeline-level error."""
    try:
        log.error(
            "notification.pipeline_error",
            signal_id=signal_id,
            error=error[:300],
            worker_id=worker_id,
        )
        # TODO: alert on-call team
    except Exception as exc:
        log.error("notification.error_notify_failed", error=str(exc)[:200])
