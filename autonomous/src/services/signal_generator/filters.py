"""
Eligibility checks for the signal generator.

Encoded as plain functions so each rule is independently testable and
log-friendly. The generator must:

  • NEVER seed signals for paused or archived bots.
  • NEVER seed signals for live or shadow bots.
  • Only seed for symbols the market-data feed can subscribe to.

Symbol support is dynamic: any `BASE/USDT` pair is supported because
Binance's public WS can stream any spot USDT pair. User-created bots
trading DOGE/USDT, ARB/USDT, etc. are fully supported — they just need
the feed to have started collecting data first.
"""
from __future__ import annotations

from typing import Any


def is_eligible_paper_bot(bot: dict[str, Any]) -> bool:
    """
    The autonomous seeder ONLY seeds for paper bots that are currently active.

      mode == "paper"
      status == "active"
      is_archived == false
    """
    if bot.get("mode") != "paper":
        return False
    if bot.get("status") != "active":
        return False
    if bot.get("is_archived"):
        return False
    return True


def is_supported_symbol(symbol: str) -> bool:
    """
    Accept any canonical `BASE/USDT` spot pair.

    The market data feed subscribes to whatever symbols active paper bots
    trade, so any valid Binance USDT pair is eligible. Rejects non-USDT
    pairs (which we cannot stream from Binance public endpoints) and
    malformed strings.
    """
    if not symbol or "/" not in symbol:
        return False
    parts = symbol.upper().split("/")
    return len(parts) == 2 and parts[1] == "USDT" and len(parts[0]) >= 1
