"""Parse free-form Telegram trading messages into normalized signal payloads."""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any


_NUMBER = r"(\d+(?:[.,]\d+)?)"
_SYMBOL_RE = re.compile(
    r"(?:#|\$)?([A-Z]{2,12})(?:[/\-_ ]?(USDT|USD|USDC|BTC|ETH))?\b",
    re.I,
)
_LONG_RE = re.compile(r"\b(long|buy|al|alış|alis)\b", re.I)
_SHORT_RE = re.compile(r"\b(short|sell|sat|satış|satis)\b", re.I)
_ENTRY_RE = re.compile(r"\b(entry|entries|giriş|giris|zone|buy zone)\b[^\d]{0,20}([0-9.,\s\-–—/]+)", re.I)
_TP_RE = re.compile(r"\b(tp|target|hedef)\s*\d*\b[^\d]{0,15}" + _NUMBER, re.I)
_SL_RE = re.compile(r"\b(sl|stop|stoploss|stop loss|zarar kes)\b[^\d]{0,15}" + _NUMBER, re.I)
_LEV_RE = re.compile(r"\b(?:lev|leverage|kaldıraç|kaldirac)\b[^\d]{0,10}" + _NUMBER + r"\s*x?", re.I)

_QUOTE_DEFAULT = "USDT"
_IGNORED_SYMBOL_WORDS = {
    "LONG",
    "SHORT",
    "ENTRY",
    "ENTRIES",
    "TARGET",
    "HEDEF",
    "STOP",
    "STOPLOSS",
    "BUY",
    "SELL",
}


@dataclass(slots=True)
class ParsedTelegramSignal:
    symbol: str | None = None
    direction: str | None = None
    entry_min: float | None = None
    entry_max: float | None = None
    take_profits: list[float] = field(default_factory=list)
    stop_loss: float | None = None
    leverage: float | None = None
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)

    @property
    def entry_price(self) -> float | None:
        if self.entry_min is None and self.entry_max is None:
            return None
        if self.entry_min is None:
            return self.entry_max
        if self.entry_max is None:
            return self.entry_min
        return (self.entry_min + self.entry_max) / 2.0

    def to_metadata(self) -> dict[str, Any]:
        return {
            "source": "telegram",
            "parser": "rule_based_v1",
            "parse_confidence": round(self.confidence, 3),
            "parse_warnings": self.warnings,
            "entry_min": self.entry_min,
            "entry_max": self.entry_max,
            "entry_price": self.entry_price,
            "take_profits": self.take_profits,
            "stop_loss": self.stop_loss,
            "leverage": self.leverage,
        }


def parse_telegram_signal(text: str) -> ParsedTelegramSignal:
    cleaned = _normalize_text(text)
    parsed = ParsedTelegramSignal()
    parsed.symbol = _extract_symbol(cleaned)
    parsed.direction = _extract_direction(cleaned)
    parsed.entry_min, parsed.entry_max = _extract_entry_range(cleaned)
    parsed.take_profits = _extract_take_profits(cleaned)
    parsed.stop_loss = _extract_stop_loss(cleaned)
    parsed.leverage = _extract_leverage(cleaned)
    parsed.warnings = _validation_warnings(parsed)
    parsed.confidence = _score(parsed)
    return parsed


def _normalize_text(text: str) -> str:
    return (
        text.replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
        .replace(",", ".")
        .strip()
    )


def _to_float(value: str) -> float | None:
    try:
        return float(value.replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def _extract_symbol(text: str) -> str | None:
    for match in _SYMBOL_RE.finditer(text):
        base = match.group(1).upper()
        quote = (match.group(2) or _QUOTE_DEFAULT).upper()
        if base in _IGNORED_SYMBOL_WORDS:
            continue
        if match.group(2) is None:
            for known_quote in ("USDT", "USDC", "USD", "BTC", "ETH"):
                if len(base) > len(known_quote) and base.endswith(known_quote):
                    return base
        if base == quote:
            continue
        return f"{base}{quote}"
    return None


def _extract_direction(text: str) -> str | None:
    long_match = _LONG_RE.search(text)
    short_match = _SHORT_RE.search(text)
    if long_match and short_match:
        return "long" if long_match.start() < short_match.start() else "short"
    if long_match:
        return "long"
    if short_match:
        return "short"
    return None


def _extract_entry_range(text: str) -> tuple[float | None, float | None]:
    match = _ENTRY_RE.search(text)
    if not match:
        return None, None
    nums = [_to_float(n) for n in re.findall(_NUMBER, match.group(2))]
    nums = [n for n in nums if n is not None]
    if not nums:
        return None, None
    if len(nums) == 1:
        return nums[0], nums[0]
    return min(nums[:2]), max(nums[:2])


def _extract_take_profits(text: str) -> list[float]:
    values: list[float] = []
    for match in _TP_RE.finditer(text):
        value = _to_float(match.group(2))
        if value is not None and value not in values:
            values.append(value)
    return values


def _extract_stop_loss(text: str) -> float | None:
    match = _SL_RE.search(text)
    if not match:
        return None
    return _to_float(match.group(2))


def _extract_leverage(text: str) -> float | None:
    match = _LEV_RE.search(text)
    if not match:
        return None
    return _to_float(match.group(1))


def _validation_warnings(parsed: ParsedTelegramSignal) -> list[str]:
    warnings: list[str] = []
    if not parsed.symbol:
        warnings.append("missing_symbol")
    if parsed.direction not in {"long", "short"}:
        warnings.append("missing_direction")
    if parsed.entry_price is None:
        warnings.append("missing_entry")
    if not parsed.take_profits:
        warnings.append("missing_take_profit")
    if parsed.stop_loss is None:
        warnings.append("missing_stop_loss")
    if parsed.direction == "long" and parsed.stop_loss and parsed.entry_price:
        if parsed.stop_loss >= parsed.entry_price:
            warnings.append("invalid_long_stop_loss")
    if parsed.direction == "short" and parsed.stop_loss and parsed.entry_price:
        if parsed.stop_loss <= parsed.entry_price:
            warnings.append("invalid_short_stop_loss")
    return warnings


def _score(parsed: ParsedTelegramSignal) -> float:
    score = 0.0
    if parsed.symbol:
        score += 0.2
    if parsed.direction:
        score += 0.2
    if parsed.entry_price is not None:
        score += 0.2
    if parsed.take_profits:
        score += 0.2
    if parsed.stop_loss is not None:
        score += 0.2
    if any(w.startswith("invalid_") for w in parsed.warnings):
        score -= 0.25
    return max(0.0, min(1.0, score))
