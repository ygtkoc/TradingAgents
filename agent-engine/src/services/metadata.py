"""
Signal metadata sanitization.

Raw signal metadata is UNTRUSTED input from external sources.
Before passing it to the pipeline, the orchestrator runs it through
this module to:

  1. Enforce a maximum byte size.
  2. Strip or ignore high-risk field names.
  3. Scan for injection patterns and flag suspicious content.
  4. Produce a sanitized copy that agents may safely read.

Agents must only read state["sanitized_metadata"].
They must never read state["signal"]["metadata"] for content decisions.

The sanitized copy is never executed as code or instructions.
It is treated as opaque metadata for logging/display only.
"""
from __future__ import annotations

import re
from typing import Any

from src.logging_config import get_logger
from src.agents.security import _scan_for_injection

log = get_logger(__name__)

# Maximum total size of sanitized metadata (bytes of str representation)
_MAX_METADATA_BYTES = 2048

# Maximum size of any single field value
_MAX_FIELD_VALUE_BYTES = 256

# Maximum number of fields allowed
_MAX_FIELD_COUNT = 20

# Field names that are silently stripped (never passed downstream)
_BLOCKED_FIELD_NAMES: frozenset[str] = frozenset({
    # Instruction-like keys
    "instruction", "instructions", "prompt", "system_prompt", "override",
    "command", "execute", "eval", "code", "script", "payload",
    # Credential-like keys
    "api_key", "secret", "password", "token", "private_key", "webhook_url",
    "callback", "exfil", "callback_url",
    # Internal pipeline keys that should never come from external signals
    "score", "decision", "veto", "confidence", "agent_name", "final_decision",
})

# Value patterns that, even in allowed fields, indicate injection
_SUSPICIOUS_VALUE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(ignore|forget|disregard)\b.{0,40}\b(instructions?|rules?|constraints?|previous)\b", re.I),
    re.compile(r"\byou are now\b|\bact as\b.{0,20}\b(admin|root|system|unrestricted)\b", re.I),
    re.compile(r"https?://[^\s]{30,}", re.I),   # Suspiciously long URLs
    re.compile(r"```|\$\(|`[^`]{5,}`|\beval\s*\(|\bexec\s*\(", re.I),
    re.compile(r"\bimport\b.{0,30}\bos\b|\bos\.system\b|\bsubprocess\b", re.I),
    re.compile(r"(--|;|\bunion\b|\bselect\b|\bdrop\b)\s+.{0,30}\b(from|into|table)\b", re.I),
    re.compile(r"\b(approve|execute|open|place)\b.{0,20}\b(trade|order|position)\b", re.I),
    re.compile(r"\bset\b.{0,20}\b(score|confidence|decision)\b.{0,20}(=|\bto\b)", re.I),
]


def sanitize_metadata(
    raw_metadata: dict[str, Any],
    signal_id: str = "unknown",
) -> tuple[dict[str, Any], bool, bool]:
    """
    Sanitizes raw signal metadata.

    Returns:
        (sanitized: dict, suspicious: bool, oversize: bool)

        sanitized:   The cleaned metadata dict safe for pipeline use.
        suspicious:  True if injection patterns were detected in any value.
        oversize:    True if the raw metadata exceeded the size limit.
    """
    if not raw_metadata:
        return {}, False, False

    raw_str = str(raw_metadata)
    oversize = len(raw_str) > _MAX_METADATA_BYTES
    suspicious = False

    # Quick full-payload scan before field-by-field processing
    if _scan_for_injection(raw_str[:_MAX_METADATA_BYTES]):
        suspicious = True
        log.warning(
            "metadata.injection_detected",
            signal_id=signal_id,
            raw_size=len(raw_str),
        )

    sanitized: dict[str, Any] = {}
    field_count = 0

    for key, value in raw_metadata.items():
        if field_count >= _MAX_FIELD_COUNT:
            log.info(
                "metadata.field_limit_reached",
                signal_id=signal_id,
                total_fields=len(raw_metadata),
                kept=field_count,
            )
            break

        # Normalise key
        key_str = str(key).strip().lower()[:64]

        # Strip blocked field names silently
        if key_str in _BLOCKED_FIELD_NAMES:
            log.warning(
                "metadata.blocked_field_stripped",
                signal_id=signal_id,
                field=key_str,
            )
            continue

        # Truncate value and scan it
        value_str = str(value)[:_MAX_FIELD_VALUE_BYTES]
        for pattern in _SUSPICIOUS_VALUE_PATTERNS:
            if pattern.search(value_str):
                suspicious = True
                log.warning(
                    "metadata.suspicious_value",
                    signal_id=signal_id,
                    field=key_str,
                    snippet=value_str[:60],
                )
                # Replace the suspicious value with a placeholder
                value_str = "[REDACTED:suspicious_content]"
                break

        sanitized[key_str] = value_str
        field_count += 1

    if oversize:
        log.info(
            "metadata.oversize_truncated",
            signal_id=signal_id,
            raw_bytes=len(raw_str),
            kept_fields=len(sanitized),
        )

    return sanitized, suspicious, oversize
