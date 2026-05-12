"""JSON helpers for the Execution Engine."""
from __future__ import annotations

import json
from typing import Any


def safe_dumps(obj: Any, **kwargs) -> str:
    """JSON-serialise with a fallback for non-serialisable types."""
    return json.dumps(obj, default=_default, **kwargs)


def safe_loads(s: str) -> Any:
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return {}


def _default(obj: Any) -> Any:
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)
