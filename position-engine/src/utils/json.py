"""JSON helpers."""
from __future__ import annotations

import json
from typing import Any


def safe_dumps(obj: Any) -> str:
    try:
        return json.dumps(obj, default=str)
    except Exception:
        return "{}"


def safe_loads(s: str) -> Any:
    try:
        return json.loads(s)
    except Exception:
        return {}
