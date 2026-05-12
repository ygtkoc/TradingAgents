"""Time utilities for the Execution Engine."""
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utcnow_iso() -> str:
    return utcnow().isoformat()


def parse_iso(s: str) -> datetime:
    """Parse an ISO 8601 string to a timezone-aware datetime."""
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def seconds_since(iso_str: str) -> float:
    """Returns seconds elapsed since the given ISO timestamp."""
    try:
        dt = parse_iso(iso_str)
        return (utcnow() - dt).total_seconds()
    except (ValueError, TypeError):
        return float("inf")
