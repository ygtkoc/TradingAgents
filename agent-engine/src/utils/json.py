"""JSON utilities for safe serialisation of Pydantic models and numpy types."""
from __future__ import annotations

import json
from typing import Any

import numpy as np


class SafeEncoder(json.JSONEncoder):
    """Handles numpy types, sets, and Pydantic models."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, set):
            return list(obj)
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        return super().default(obj)


def safe_dumps(obj: Any, **kwargs: Any) -> str:
    return json.dumps(obj, cls=SafeEncoder, **kwargs)


def safe_loads(s: str) -> Any:
    return json.loads(s)
