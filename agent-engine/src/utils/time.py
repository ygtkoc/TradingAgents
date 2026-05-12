"""Timezone-aware datetime helpers."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def utcnow_iso() -> str:
    return utcnow().isoformat()


def parse_iso(value: str) -> datetime:
    """Parse an ISO 8601 string, always returning a UTC-aware datetime."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def minutes_since(dt: datetime) -> float:
    """Returns minutes elapsed since dt (positive = dt is in the past)."""
    return (utcnow() - dt).total_seconds() / 60.0


def is_stale(timestamp: Optional[str], max_age_minutes: int) -> bool:
    """Returns True if the timestamp is older than max_age_minutes."""
    if timestamp is None:
        return True
    try:
        dt = parse_iso(timestamp)
        return minutes_since(dt) > max_age_minutes
    except (ValueError, TypeError):
        return True
