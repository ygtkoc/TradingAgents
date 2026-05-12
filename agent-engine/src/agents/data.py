"""
Data category agents.
These run first in the pipeline to gather and validate market data.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from src.agents.base import BaseAgent
from src.db.models import AgentDecision, AgentOutputResult
from src.services.market_data import (
    calculate_spread_pct,
    get_latest_snapshot,
    get_price_history,
    extract_closes,
)
from src.services.indicators import compute_rsi
from src.config import settings
from src.utils.time import is_stale

if TYPE_CHECKING:
    from src.orchestration.state import PipelineState


class MarketDataAgent(BaseAgent):
    """
    Fetches the latest market snapshot for the signal's symbol.
    Stores it in pipeline state for downstream agents.
    Decision: does not recommend a trade direction — scores data availability.
    """

    async def _execute(self, state: "PipelineState") -> AgentOutputResult:
        signal = state["signal"]
        exchange = signal.exchange
        symbol = signal.symbol

        snapshot = await get_latest_snapshot(
            exchange=exchange,
            symbol=symbol,
            timeframe="1h",
        )

        if snapshot is None:
            return self._make_result(
                decision=AgentDecision.REJECT,
                score=-100.0,
                confidence=1.0,
                reasoning=f"No market snapshot available for {symbol} on {exchange}.",
                risk_flags=["no_market_data"],
                recommendations=["Ensure market data agent is running and populating snapshots"],
            )

        # Store snapshot in state for downstream agents
        state["market_snapshot"] = snapshot.model_dump()

        # Fetch price history for indicator agents.
        # 150 bars covers all indicator warm-up requirements:
        #   - EMA(50), SMA(50) need 50 bars
        #   - MACD(26+9) needs 35 bars
        #   - ATR(14), RSI(14) need 15 bars
        #   - Warmup gate (candles_required=100) needs 100 bars
        history = await get_price_history(exchange, symbol, "1h", limit=150)
        state["price_history"] = [s.model_dump() for s in history]

        # Also fetch shorter timeframe for intraday context (best-effort)
        try:
            history_5m = await get_price_history(exchange, symbol, "5m", limit=60)
            state["price_history_5m"] = [s.model_dump() for s in history_5m]
        except Exception:
            state["price_history_5m"] = []

        effective_direction = _resolve_effective_direction(signal.direction.value, history)
        state["effective_direction"] = effective_direction

        indicators = snapshot.technical_indicators or {}
        stale = is_stale(snapshot.captured_at, settings.max_stale_snapshot_minutes)

        score = 80.0 if not stale else 30.0
        confidence = 0.9 if not stale else 0.5

        return self._make_result(
            decision=AgentDecision.WAIT,   # Data agent does not decide direction
            score=score,
            confidence=confidence,
            reasoning=(
                f"Market snapshot loaded for {symbol} on {exchange}. "
                f"Price: {snapshot.close_price}. "
                f"Stale: {stale}. "
                f"Indicators available: {list(indicators.keys())}"
            ),
            output={
                "close_price": snapshot.close_price,
                "volume": snapshot.volume,
                "captured_at": snapshot.captured_at,
                "stale": stale,
                "timeframe": snapshot.timeframe,
                "indicators_available": list(indicators.keys()),
                "history_bars": len(history),
                "effective_direction": effective_direction,
            },
            risk_flags=["stale_data"] if stale else [],
        )


class DataQualityAgent(BaseAgent):
    """
    Validates the market snapshot quality.
    Can veto if data quality is critically bad (missing data, extreme spread).
    This is a GATE agent — its veto short-circuits the entire pipeline.

    can_veto = True (set in agent_definitions DB row)
    """

    async def _execute(self, state: "PipelineState") -> AgentOutputResult:
        snapshot_dict = state.get("market_snapshot")
        signal = state["signal"]

        if not snapshot_dict:
            return self._safe_veto(
                reason="No market snapshot in state. Cannot validate data quality.",
                severity_flags=["critical_data_missing"],
            )

        from src.db.models import MarketSnapshot
        snapshot = MarketSnapshot.model_validate(snapshot_dict)

        issues: list[str] = []
        flags: list[str] = []
        penalty = 0.0

        # ── Staleness check ───────────────────────────────────────────────────
        stale = is_stale(snapshot.captured_at, settings.max_stale_snapshot_minutes)
        if stale:
            issues.append(
                f"Snapshot is stale (captured_at={snapshot.captured_at}, "
                f"max_age={settings.max_stale_snapshot_minutes}m)"
            )
            flags.append("stale_data")
            penalty += 20.0

        # ── Price sanity check ────────────────────────────────────────────────
        if snapshot.close_price <= 0:
            return self._safe_veto(
                "Invalid close price (<= 0). Possible data corruption.",
                ["invalid_price"],
            )

        if snapshot.high_price < snapshot.low_price:
            return self._safe_veto(
                "High price < Low price. Corrupted OHLCV data.",
                ["corrupted_ohlcv"],
            )

        if snapshot.close_price > snapshot.high_price * 1.01:
            issues.append("Close > High by >1%. Possible data error.")
            flags.append("ohlcv_inconsistency")
            penalty += 10.0

        # ── Spread check ─────────────────────────────────────────────────────
        spread = calculate_spread_pct(snapshot)
        if spread is not None:
            if spread > settings.manipulation_spread_threshold_pct:
                issues.append(
                    f"Spread {spread:.2f}% exceeds threshold "
                    f"{settings.manipulation_spread_threshold_pct:.2f}%"
                )
                flags.append("abnormal_spread")
                penalty += 25.0

        # ── Volume check ──────────────────────────────────────────────────────
        if snapshot.volume <= 0:
            issues.append("Zero volume. Possibly illiquid or data error.")
            flags.append("zero_volume")
            penalty += 15.0

        # ── Compute quality score ─────────────────────────────────────────────
        quality_score = max(0.0, 100.0 - penalty)
        confidence = 0.9 - (penalty / 200.0)
        state["data_quality_score"] = quality_score
        state["data_quality_penalty"] = penalty

        # Critical failure: veto
        if quality_score < 30.0:
            return self._safe_veto(
                f"Data quality too low ({quality_score:.1f}/100). Issues: {'; '.join(issues)}",
                flags,
            )

        decision = AgentDecision.WAIT if issues else AgentDecision.WAIT
        return self._make_result(
            decision=decision,
            score=quality_score - 50.0,  # Centre around 0: 100 quality → +50
            confidence=max(0.1, confidence),
            reasoning=(
                f"Data quality: {quality_score:.1f}/100. "
                + (f"Issues: {'; '.join(issues)}" if issues else "No issues detected.")
            ),
            output={
                "quality_score": quality_score,
                "penalty": penalty,
                "spread_pct": spread,
                "stale": stale,
                "issues": issues,
            },
            risk_flags=flags,
            recommendations=(
                ["Check market data pipeline for freshness issues"] if stale else []
            ),
        )


def _resolve_effective_direction(intended_direction: str, history: list) -> str:
    if intended_direction in {"long", "short"}:
        return intended_direction

    closes = extract_closes(history)
    if len(closes) < 5:
        return "neutral"

    last_close = closes[-1]
    short_anchor = closes[-5]
    long_anchor = closes[0]
    short_momentum = ((last_close - short_anchor) / short_anchor * 100) if short_anchor else 0.0
    long_momentum = ((last_close - long_anchor) / long_anchor * 100) if long_anchor else 0.0

    # Use a tighter threshold (0.10%) so modest price movements still generate
    # a directional signal. The aggregator and risk agents then gate quality.
    if short_momentum >= 0.10 and long_momentum >= -0.5:
        return "long"
    if short_momentum <= -0.10 and long_momentum <= 0.5:
        return "short"
    if short_momentum > 0:
        return "long"
    if short_momentum < 0:
        return "short"
    return "neutral"
