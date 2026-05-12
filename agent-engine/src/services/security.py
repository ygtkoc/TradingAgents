"""
Security check helpers shared across the security agent layer and orchestrator.

These are pure functions — they do NOT read from the database.
They are intentionally kept simple and deterministic to avoid introducing
new attack surfaces in the security layer itself.
"""
from __future__ import annotations

import re
from typing import Optional


# Valid trading symbol: ASSET/QUOTE with optional :SETTLE suffix
_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]{1,20}(/[A-Z0-9]{1,10})?(:USDT)?$")

# Valid exchange identifiers (lowercase alphanumeric + hyphen/underscore)
_EXCHANGE_PATTERN = re.compile(r"^[a-z0-9_\-]{1,30}$")

# Allowlist of known exchanges (extend as needed)
_KNOWN_EXCHANGES: frozenset[str] = frozenset({
    "binance", "binanceus", "bybit", "okx", "kraken", "coinbase",
    "bitget", "kucoin", "gate", "mexc", "huobi", "phemex",
    "bitmex", "deribit", "bitfinex", "gemini", "bitstamp",
    # Sandbox / test exchanges
    "binance_testnet", "bybit_testnet",
})

# Maximum allowed metadata payload size (bytes)
_MAX_METADATA_BYTES = 4096


def validate_symbol(symbol: str) -> tuple[bool, Optional[str]]:
    """
    Returns (valid: bool, error: str | None).
    """
    if not symbol:
        return False, "Symbol is empty"
    if not _SYMBOL_PATTERN.match(symbol):
        return False, f"Symbol '{symbol}' does not match expected format (e.g. BTC/USDT)"
    return True, None


def validate_exchange(exchange: str) -> tuple[bool, Optional[str]]:
    """
    Returns (valid: bool, error: str | None).
    Warns (but does not block) on unknown exchanges.
    """
    if not exchange:
        return False, "Exchange is empty"
    if not _EXCHANGE_PATTERN.match(exchange):
        return False, f"Exchange '{exchange}' contains invalid characters"
    return True, None


def is_known_exchange(exchange: str) -> bool:
    """Returns True if the exchange is in the known-exchange allowlist."""
    return exchange.lower() in _KNOWN_EXCHANGES


def validate_metadata_size(metadata: dict) -> tuple[bool, Optional[str]]:
    """
    Checks that the metadata payload does not exceed the size limit.
    """
    size = len(str(metadata))
    if size > _MAX_METADATA_BYTES:
        return False, f"Metadata too large: {size} bytes (max {_MAX_METADATA_BYTES})"
    return True, None


def sanitize_string(value: str, max_length: int = 500) -> str:
    """
    Strips leading/trailing whitespace and truncates to max_length.
    Does NOT HTML-escape — this is for internal logging only.
    """
    return value.strip()[:max_length]


def is_safe_for_logging(value: str) -> bool:
    """
    Returns False if the string contains characters that could
    corrupt structured log output (null bytes, ANSI escape codes).
    """
    if "\x00" in value:
        return False
    if re.search(r"\x1b\[", value):  # ANSI escape
        return False
    return True
