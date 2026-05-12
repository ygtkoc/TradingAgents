"""
Critique category agents.
These agents challenge the proposed trade and look for failure scenarios.
They score negatively when they find problems, positively when the trade
withstands scrutiny. They do NOT have veto power.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from src.agents.base import BaseAgent
from src.db.models import AgentDecision, AgentOutputResult
from src.services import indicators as ind
from src.services.market_data import (
    calculate_spread_pct,
    extract_closes,
    extract_volumes,
)

if TYPE_CHECKING:
    from src.orchestration.state import PipelineState


def _get_direction(state: "PipelineState") -> str:
    signal = state["signal"]
    return state.get("effective_direction") or signal.direction.value


class ContrarianAgent(BaseAgent):
    """
    Argues against the proposed trade by actively seeking failure scenarios.
    Examines whether the signal direction is premature, overextended,
    or contradicted by multi-timeframe context.

    A high contrarian score means the trade survives scrutiny.
    A low score means significant counter-evidence was found.
    """

    async def _execute(self, state: "PipelineState") -> AgentOutputResult:
        signal = state["signal"]
        intended = _get_direction(state)
        snapshots_raw = state.get("price_history", [])

        if len(snapshots_raw) < 10:
            return self._make_result(
                decision=AgentDecision.WAIT,
                score=0.0,
                confidence=0.1,
                reasoning="Insufficient history for contrarian analysis.",
                risk_flags=["insufficient_history"],
            )

        from src.db.models import MarketSnapshot
        snapshots = [MarketSnapshot.model_validate(s) for s in snapshots_raw]
        closes = extract_closes(snapshots)
        volumes = extract_volumes(snapshots)

        objections: list[tuple[str, float]] = []  # (description, score_delta)
        flags: list[str] = []

        # ── Test 1: Is momentum already exhausted? ────────────────────────────
        # If we're going long, a big recent run-up suggests overextension.
        mom_5 = ind.price_momentum(closes, lookback=5)
        mom_20 = ind.price_momentum(closes, lookback=20) if len(closes) > 21 else None

        if mom_5 is not None and mom_20 is not None:
            if intended == "long" and mom_5 > 8.0:
                objections.append(
                    (f"Possible momentum exhaustion: +{mom_5:.1f}% in 5 bars", -25.0)
                )
                flags.append("momentum_exhaustion")
            elif intended == "short" and mom_5 < -8.0:
                objections.append(
                    (f"Possible momentum exhaustion: {mom_5:.1f}% in 5 bars", -25.0)
                )
                flags.append("momentum_exhaustion")
            else:
                objections.append(("No momentum exhaustion detected", 15.0))
        elif mom_5 is not None:
            objections.append(("Single-timeframe momentum check only", 5.0))

        # ── Test 2: Trend reversal risk ───────────────────────────────────────
        # Is the price approaching a structural reversal zone?
        trend = ind.detect_trend(closes, short=20, long=50)
        if trend is not None:
            if intended == "long" and trend == "downtrend":
                objections.append(("Trading long against downtrend — reversal risk", -30.0))
                flags.append("counter_trend")
            elif intended == "short" and trend == "uptrend":
                objections.append(("Trading short against uptrend — squeeze risk", -30.0))
                flags.append("counter_trend")
            elif (intended == "long" and trend == "uptrend") or (
                intended == "short" and trend == "downtrend"
            ):
                objections.append(("Trade aligns with trend — survives trend test", 25.0))
            else:
                objections.append(("Sideways trend — directional risk both ways", -10.0))

        # ── Test 3: Volume declining on trend ─────────────────────────────────
        # A move without volume backing it is suspect.
        vol_ratio = ind.volume_momentum(volumes, lookback=5)
        if vol_ratio is not None:
            if vol_ratio < 0.6:
                objections.append((f"Volume declining ({vol_ratio:.2f}x avg) — weak conviction", -20.0))
                flags.append("declining_volume")
            elif vol_ratio >= 1.2:
                objections.append((f"Strong volume ({vol_ratio:.2f}x avg) — conviction present", 15.0))
            else:
                objections.append((f"Average volume ({vol_ratio:.2f}x avg)", 5.0))

        # ── Test 4: Recent price rejection ────────────────────────────────────
        # Check if price has tried and failed to move in the intended direction.
        if len(closes) >= 10:
            recent_closes = closes[-10:]
            if intended == "long":
                # Check for lower highs in recent bars (rejection pattern)
                recent_highs = [max(recent_closes[i:i+3]) for i in range(0, len(recent_closes)-2, 2)]
                if len(recent_highs) >= 2 and recent_highs[-1] < recent_highs[-2]:
                    objections.append(("Recent lower highs suggest upside rejection", -15.0))
                    flags.append("upper_rejection")
                else:
                    objections.append(("No clear upside rejection in recent bars", 10.0))
            elif intended == "short":
                recent_lows = [min(recent_closes[i:i+3]) for i in range(0, len(recent_closes)-2, 2)]
                if len(recent_lows) >= 2 and recent_lows[-1] > recent_lows[-2]:
                    objections.append(("Recent higher lows suggest downside rejection", -15.0))
                    flags.append("lower_rejection")
                else:
                    objections.append(("No clear downside rejection in recent bars", 10.0))

        # ── Test 5: RSI divergence check ──────────────────────────────────────
        rsi = ind.compute_rsi(closes, 14)
        if rsi is not None:
            if intended == "long" and rsi > 65:
                objections.append((f"RSI {rsi:.1f} — entering overbought before entry", -15.0))
                flags.append("pre_entry_overbought")
            elif intended == "short" and rsi < 35:
                objections.append((f"RSI {rsi:.1f} — entering oversold before short", -15.0))
                flags.append("pre_entry_oversold")
            else:
                objections.append((f"RSI {rsi:.1f} acceptable for {intended}", 10.0))

        # ── Aggregate ─────────────────────────────────────────────────────────
        total = sum(v for _, v in objections)
        score = max(-100.0, min(100.0, total))
        confidence = min(0.85, 0.3 + len(objections) * 0.08)

        decision = (
            AgentDecision.WAIT if score < 10 else
            AgentDecision.OPEN_LONG if intended == "long" else
            AgentDecision.OPEN_SHORT
        )

        return self._make_result(
            decision=decision,
            score=score,
            confidence=confidence,
            reasoning=(
                f"Contrarian analysis for {signal.symbol} ({intended}): "
                + "; ".join(f"{name}({v:+.0f})" for name, v in objections)
            ),
            output={
                "trend": trend,
                "rsi": rsi,
                "momentum_5bar": mom_5,
                "momentum_20bar": mom_20,
                "volume_ratio": vol_ratio,
                "objections": [{"name": n, "score": v} for n, v in objections],
            },
            risk_flags=flags,
        )


class ManipulationDetectionAgent(BaseAgent):
    """
    Detects pump-and-dump patterns, wash trading, and abnormal market conditions.
    High score means the market looks clean.
    Low score (with flags) means manipulation is suspected.

    This agent does NOT veto — it scores. The RiskAuditorAgent and
    SecurityGuardianAgent may veto based on accumulated flags.
    """

    async def _execute(self, state: "PipelineState") -> AgentOutputResult:
        snapshot_dict = state.get("market_snapshot")
        signal = state["signal"]
        snapshots_raw = state.get("price_history", [])

        if not snapshot_dict:
            return self._make_result(
                decision=AgentDecision.WAIT,
                score=0.0,
                confidence=0.1,
                reasoning="No market snapshot available for manipulation detection.",
                risk_flags=["no_snapshot"],
            )

        from src.db.models import MarketSnapshot
        snapshot = MarketSnapshot.model_validate(snapshot_dict)
        snapshots = [MarketSnapshot.model_validate(s) for s in snapshots_raw]

        findings: list[tuple[str, float]] = []
        flags: list[str] = []

        # ── Check 1: Abnormal spread ──────────────────────────────────────────
        from src.config import settings
        spread = calculate_spread_pct(snapshot)
        if spread is not None:
            if spread > settings.manipulation_spread_threshold_pct * 2:
                findings.append((f"Extreme spread {spread:.2f}%", -40.0))
                flags.append("extreme_spread")
            elif spread > settings.manipulation_spread_threshold_pct:
                findings.append((f"High spread {spread:.2f}%", -20.0))
                flags.append("high_spread")
            else:
                findings.append((f"Normal spread {spread:.2f}%", 20.0))
        else:
            findings.append(("Spread data unavailable", -5.0))

        # ── Check 2: Volume spike detection ───────────────────────────────────
        if len(snapshots) >= 20:
            closes = extract_closes(snapshots)
            volumes = extract_volumes(snapshots)
            vol_ratio = ind.volume_momentum(volumes, lookback=3)

            if vol_ratio is not None:
                if vol_ratio > 5.0:
                    findings.append((f"Extreme volume spike {vol_ratio:.1f}x avg", -35.0))
                    flags.append("extreme_volume_spike")
                elif vol_ratio > 3.0:
                    findings.append((f"High volume spike {vol_ratio:.1f}x avg — monitor", -15.0))
                    flags.append("volume_spike")
                elif vol_ratio >= 0.5:
                    findings.append((f"Volume within normal range {vol_ratio:.1f}x avg", 15.0))
                else:
                    findings.append((f"Abnormally low volume {vol_ratio:.1f}x avg", -10.0))
                    flags.append("suspiciously_low_volume")

            # ── Check 3: Pump detection — rapid price spike ──────────────────
            # Looks for a rapid price increase that outpaces volume normalcy
            if len(closes) >= 10:
                recent_mom = ind.price_momentum(closes, lookback=3)
                if recent_mom is not None:
                    if abs(recent_mom) > 15.0 and (vol_ratio is not None and vol_ratio > 3.0):
                        findings.append(
                            (f"Rapid {recent_mom:.1f}% move with high volume — possible pump", -40.0)
                        )
                        flags.append("potential_pump")
                    elif abs(recent_mom) > 10.0 and (vol_ratio is None or vol_ratio < 1.0):
                        findings.append(
                            (f"Sharp {recent_mom:.1f}% move without volume — possible manipulation", -30.0)
                        )
                        flags.append("low_volume_spike")
                    elif abs(recent_mom) <= 5.0:
                        findings.append((f"Orderly price movement {recent_mom:+.1f}%", 15.0))
                    else:
                        findings.append((f"Elevated price movement {recent_mom:+.1f}%", -5.0))

            # ── Check 4: Price-volume divergence ─────────────────────────────
            # Sustained price move with declining volume suggests wash trading or fading
            if len(closes) >= 20 and len(volumes) >= 20:
                price_change_10 = ind.price_momentum(closes, lookback=10)
                recent_vols = volumes[-5:]
                older_vols = volumes[-15:-5]
                avg_recent_vol = sum(recent_vols) / len(recent_vols)
                avg_older_vol = sum(older_vols) / len(older_vols)
                vol_declining = avg_older_vol > 0 and (avg_recent_vol / avg_older_vol) < 0.6

                if price_change_10 is not None and abs(price_change_10) > 5.0 and vol_declining:
                    findings.append(("Price-volume divergence — declining volume on move", -20.0))
                    flags.append("price_volume_divergence")
                else:
                    findings.append(("No significant price-volume divergence", 10.0))

        # ── Check 5: OHLC consistency ─────────────────────────────────────────
        # Inconsistent OHLC data suggests feed manipulation or data corruption
        if snapshot.high_price and snapshot.low_price and snapshot.close_price and snapshot.open_price:
            price_range = snapshot.high_price - snapshot.low_price
            if price_range > 0:
                # Check if close is within range
                if snapshot.low_price <= snapshot.close_price <= snapshot.high_price:
                    findings.append(("OHLCV data internally consistent", 10.0))
                else:
                    findings.append(("Close outside high-low range — data anomaly", -25.0))
                    flags.append("ohlcv_anomaly")

                # Unusually long wicks relative to body
                body = abs(snapshot.close_price - snapshot.open_price)
                wick_ratio = body / price_range if price_range > 0 else 1.0
                if wick_ratio < 0.05:
                    findings.append(("Doji candle with tiny body — indecision/manipulation possible", -10.0))
                    flags.append("doji_pattern")

        # ── Aggregate ─────────────────────────────────────────────────────────
        total = sum(v for _, v in findings)
        score = max(-100.0, min(100.0, total))
        confidence = 0.8 if len(findings) >= 4 else 0.5

        # Persist manipulation flags to state for downstream risk agents
        existing_flags = state.get("manipulation_flags", [])
        state["manipulation_flags"] = list(set(existing_flags + flags))
        state["manipulation_score_penalty"] = max(0.0, -score) if score < 0 else 0.0

        decision = AgentDecision.WAIT if flags else AgentDecision.WAIT  # Non-directional

        return self._make_result(
            decision=decision,
            score=score,
            confidence=confidence,
            reasoning=(
                f"Manipulation scan for {signal.symbol}: "
                + "; ".join(f"{name}({v:+.0f})" for name, v in findings)
            ),
            output={
                "spread_pct": spread,
                "manipulation_flags": flags,
                "findings": [{"name": n, "score": v} for n, v in findings],
                "clean": len(flags) == 0,
            },
            risk_flags=flags,
        )
