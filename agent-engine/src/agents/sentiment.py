"""
Sentiment analysis agents.

MarketSentimentAgent — reads on-chain / fear-greed / news signals.
Uses CryptoPanic (free public API, no key required for basic calls) to
classify recent crypto news as bullish, bearish, or neutral.

Design principles:
  - News is NEVER the sole reason for a trade.
  - The agent contributes a small sentiment score (max ±20) so it can
    only tip the balance when technical and price-action signals are
    already aligned.
  - If the news API is unavailable the agent returns WAIT with score=0
    so the pipeline continues uninterrupted.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Optional

import httpx

from src.agents.base import BaseAgent
from src.db.models import AgentDecision, AgentOutputResult
from src.logging_config import get_logger

if TYPE_CHECKING:
    from src.orchestration.state import PipelineState

log = get_logger(__name__)

# Public CryptoPanic API (no auth required for basic endpoints).
_CRYPTOPANIC_URL = "https://cryptopanic.com/api/v1/posts/"
_HTTP_TIMEOUT    = 4.0   # seconds — pipeline can't wait long


def _extract_base_currency(symbol: str) -> str:
    """BTC/USDT → BTC, ETH-USDT → ETH, BTCUSDT → BTC (best-effort)."""
    for sep in ("/", "-", "_"):
        if sep in symbol:
            return symbol.split(sep)[0].upper()
    # No separator: assume first 3-4 chars are the base
    return symbol[:4].upper() if len(symbol) > 5 else symbol.upper()


def _score_headlines(titles: list[str], base: str) -> tuple[int, int, int, list[str]]:
    """
    Simple keyword-based headline scorer.

    Returns (bullish_count, bearish_count, neutral_count, matched_titles).
    """
    BULLISH = {
        "surge", "rally", "soar", "gain", "bull", "breakout", "buy",
        "adoption", "upgrade", "partnership", "milestone", "record",
        "approval", "etf", "listing", "integration", "launch",
        "bullish", "rise", "rises", "rising", "recover", "recovery",
        "institutional", "investment", "accumulate",
    }
    BEARISH = {
        "crash", "drop", "plunge", "fall", "bear", "dump", "sell",
        "hack", "exploit", "scam", "fraud", "ban", "regulation",
        "bearish", "decline", "declining", "lose", "loss", "lawsuit",
        "investigation", "shutdown", "delist", "warning", "risk",
        "vulnerable", "liquidation", "bankruptcy",
    }

    b_pos = b_neg = b_neu = 0
    matched: list[str] = []

    for title in titles:
        lower = title.lower()
        # Only count if the base currency is mentioned
        if base.lower() not in lower and "crypto" not in lower:
            continue
        matched.append(title[:80])
        words = set(lower.split())
        pos_hits = words & BULLISH
        neg_hits = words & BEARISH
        if pos_hits and not neg_hits:
            b_pos += 1
        elif neg_hits and not pos_hits:
            b_neg += 1
        else:
            b_neu += 1

    return b_pos, b_neg, b_neu, matched


async def _fetch_cryptopanic(currencies: str, timeout: float) -> list[str]:
    """Calls CryptoPanic public API and returns a list of headline titles."""
    params = {
        "public": "true",
        "currencies": currencies,
        "kind": "news",
        "filter": "important",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(_CRYPTOPANIC_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results") or []
            return [r.get("title", "") for r in results if r.get("title")]
    except Exception as exc:
        log.info("sentiment.news_fetch_failed", error=str(exc)[:120])
        return []


class MarketSentimentAgent(BaseAgent):
    """
    Classifies recent news sentiment for the signal's base currency.

    Contribution: ±20 points max (bullish news = +20, bearish = -20).
    Falls back to score=0 (neutral) if news API is unavailable.
    Does NOT veto — it is a soft signal only.
    """

    async def _execute(self, state: "PipelineState") -> AgentOutputResult:
        signal   = state["signal"]
        intended = state.get("effective_direction") or signal.direction.value
        base     = _extract_base_currency(signal.symbol)

        # ── Fetch headlines with a generous timeout ───────────────────────────
        titles = await _fetch_cryptopanic(base, timeout=_HTTP_TIMEOUT)

        if not titles:
            return self._make_result(
                decision=AgentDecision.WAIT,
                score=0.0,
                confidence=0.1,
                reasoning=f"No recent {base} headlines available — sentiment neutral.",
                output={
                    "base_currency":  base,
                    "headlines_found": 0,
                    "sentiment":      "neutral",
                    "bullish":        0,
                    "bearish":        0,
                    "neutral":        0,
                },
            )

        bullish, bearish, neutral_c, matched = _score_headlines(titles, base)
        total_scored = bullish + bearish + neutral_c

        # Sentiment ratio
        if total_scored == 0:
            sentiment     = "neutral"
            raw_score     = 0.0
        elif bullish > bearish:
            sentiment     = "bullish"
            ratio         = (bullish - bearish) / total_scored
            raw_score     = ratio * 20.0        # max +20
        elif bearish > bullish:
            sentiment     = "bearish"
            ratio         = (bearish - bullish) / total_scored
            raw_score     = -(ratio * 20.0)     # max -20
        else:
            sentiment     = "mixed"
            raw_score     = 0.0

        # Align with intended direction
        if intended == "long":
            score = raw_score
        elif intended == "short":
            score = -raw_score
        else:
            score = 0.0

        confidence = min(0.6, 0.1 + total_scored * 0.05)

        log.info(
            "sentiment.scored",
            symbol=signal.symbol,
            base=base,
            direction=intended,
            sentiment=sentiment,
            bullish=bullish,
            bearish=bearish,
            neutral=neutral_c,
            score=round(score, 2),
            headlines_matched=len(matched),
        )

        return self._make_result(
            decision=AgentDecision.WAIT,  # sentiment never directly decides
            score=score,
            confidence=confidence,
            reasoning=(
                f"News sentiment for {base}: {sentiment} "
                f"(+{bullish} bullish, -{bearish} bearish, ~{neutral_c} neutral "
                f"from {len(titles)} headlines). "
                f"Score contribution: {score:+.1f}"
            ),
            output={
                "base_currency":      base,
                "headlines_fetched":  len(titles),
                "headlines_matched":  len(matched),
                "bullish":            bullish,
                "bearish":            bearish,
                "neutral_count":      neutral_c,
                "sentiment":          sentiment,
                "raw_score":          raw_score,
                "matched_titles":     matched[:5],
            },
        )
