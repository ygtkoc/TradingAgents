"""
Analysis category agents.
Produce directional signals from technical and price/volume analysis.
These agents do NOT have veto power — they contribute scores.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from src.agents.base import BaseAgent
from src.db.models import AgentDecision, AgentOutputResult, TradeDirection
from src.services import indicators as ind
from src.services.market_data import (
    extract_closes, extract_highs, extract_lows, extract_volumes,
)
from src.logging_config import get_logger

if TYPE_CHECKING:
    from src.orchestration.state import PipelineState

log = get_logger(__name__)


def _direction_to_decision(
    direction: str, score: float
) -> AgentDecision:
    """Maps signal direction + score to the agent's decision enum."""
    if score < 10:
        return AgentDecision.WAIT
    if direction == "long":
        return AgentDecision.OPEN_LONG
    if direction == "short":
        return AgentDecision.OPEN_SHORT
    return AgentDecision.WAIT


def _get_snapshots(state: "PipelineState"):
    """Reconstruct snapshot list from state; returns empty list if unavailable."""
    from src.db.models import MarketSnapshot
    history = state.get("price_history", [])
    return [MarketSnapshot.model_validate(s) for s in history]


def _get_direction(state: "PipelineState") -> str:
    signal = state["signal"]
    return state.get("effective_direction") or signal.direction.value


class TechnicalAnalysisAgent(BaseAgent):
    """
    Comprehensive technical analysis: RSI, EMA/SMA crossovers, MACD, Bollinger
    Bands, ATR, VWAP, Stochastic, CCI, volume spikes, and support/resistance.

    Multi-timeframe: scores from 1h (primary) and 5m (intraday confirmation).
    Agents do NOT veto — they contribute directional scores.
    """

    async def _execute(self, state: "PipelineState") -> AgentOutputResult:
        signal = state["signal"]
        intended = _get_direction(state)

        snapshots = _get_snapshots(state)
        if not snapshots:
            return self._make_result(
                decision=AgentDecision.WAIT,
                score=0.0,
                confidence=0.1,
                reasoning="No price history available for technical analysis.",
                risk_flags=["insufficient_history"],
            )

        closes  = extract_closes(snapshots)
        highs   = extract_highs(snapshots)
        lows    = extract_lows(snapshots)
        volumes = extract_volumes(snapshots)
        current_price = closes[-1] if closes else 0.0

        # ── Primary indicators (1h) ───────────────────────────────────────────
        rsi           = ind.compute_rsi(closes, 14)
        ema_9         = ind.compute_ema(closes, 9)
        ema_21        = ind.compute_ema(closes, 21)
        ema_50        = ind.compute_ema(closes, 50)
        sma_20        = ind.compute_sma(closes, 20)
        sma_50        = ind.compute_sma(closes, 50)
        macd_line, macd_sig, macd_hist = ind.compute_macd(closes)
        bb_upper, bb_mid, bb_lower     = ind.compute_bollinger_bands(closes)
        atr           = ind.compute_atr(highs, lows, closes, 14)
        vwap          = ind.compute_vwap(highs, lows, closes, volumes)
        stoch_k, _    = ind.compute_stochastic(highs, lows, closes, 14, 3)
        cci           = ind.compute_cci(highs, lows, closes, 20)
        vol_spike     = ind.detect_volume_spike(volumes, lookback=20, spike_threshold=2.5)
        sr            = ind.detect_support_resistance(closes, lows, highs, lookback=20)
        structure     = ind.detect_higher_highs_lower_lows(highs, lows, lookback=5)

        # ── Intraday 5m confirmation (best-effort) ────────────────────────────
        from src.db.models import MarketSnapshot
        raw_5m   = state.get("price_history_5m", [])
        snaps_5m = [MarketSnapshot.model_validate(s) for s in raw_5m] if raw_5m else []
        rsi_5m   = ind.compute_rsi(extract_closes(snaps_5m), 14) if len(snaps_5m) >= 15 else None
        macd_5m  = ind.compute_macd(extract_closes(snaps_5m))[2] if len(snaps_5m) >= 36 else None

        signals: list[tuple[str, float]] = []
        flags:   list[str] = []
        notes:   list[str] = []

        # ── RSI (1h) ─────────────────────────────────────────────────────────
        if rsi is not None:
            if intended == "long":
                if rsi < 30:
                    signals.append(("RSI oversold <30", 30.0))
                elif rsi < 45:
                    signals.append(("RSI low (long-friendly)", 15.0))
                elif rsi > 70:
                    signals.append(("RSI overbought >70", -25.0))
                    flags.append("rsi_overbought_long")
                else:
                    signals.append(("RSI neutral", 5.0))
            elif intended == "short":
                if rsi > 70:
                    signals.append(("RSI overbought >70", 30.0))
                elif rsi > 55:
                    signals.append(("RSI elevated (short-friendly)", 15.0))
                elif rsi < 30:
                    signals.append(("RSI oversold <30", -25.0))
                    flags.append("rsi_oversold_short")
                else:
                    signals.append(("RSI neutral", 5.0))

        # ── EMA stack ────────────────────────────────────────────────────────
        if ema_9 is not None and ema_21 is not None and ema_50 is not None:
            bullish_stack = ema_9 > ema_21 > ema_50
            bearish_stack = ema_9 < ema_21 < ema_50
            if intended == "long":
                if bullish_stack:
                    signals.append(("EMA bullish stack 9>21>50", 25.0))
                elif ema_9 > ema_21:
                    signals.append(("EMA short-term bullish", 10.0))
                else:
                    signals.append(("EMA bearish on long", -20.0))
                    flags.append("ema_bearish_on_long")
            elif intended == "short":
                if bearish_stack:
                    signals.append(("EMA bearish stack 9<21<50", 25.0))
                elif ema_9 < ema_21:
                    signals.append(("EMA short-term bearish", 10.0))
                else:
                    signals.append(("EMA bullish on short", -20.0))

        # ── SMA trend (slower, confirms major direction) ─────────────────────
        if sma_20 is not None and sma_50 is not None:
            if intended == "long" and sma_20 > sma_50:
                signals.append(("SMA20 > SMA50 (bullish)", 12.0))
            elif intended == "short" and sma_20 < sma_50:
                signals.append(("SMA20 < SMA50 (bearish)", 12.0))

        # ── MACD (1h) ────────────────────────────────────────────────────────
        if macd_hist is not None and macd_line is not None:
            if intended == "long":
                if macd_hist > 0 and macd_line > 0:
                    signals.append(("MACD bullish histogram + line above zero", 20.0))
                elif macd_hist > 0:
                    signals.append(("MACD bullish histogram", 12.0))
                else:
                    signals.append(("MACD bearish histogram", -12.0))
            elif intended == "short":
                if macd_hist < 0 and macd_line < 0:
                    signals.append(("MACD bearish histogram + line below zero", 20.0))
                elif macd_hist < 0:
                    signals.append(("MACD bearish histogram", 12.0))
                else:
                    signals.append(("MACD bullish histogram", -12.0))

        # ── Bollinger Bands ───────────────────────────────────────────────────
        if bb_lower is not None and bb_upper is not None and current_price > 0:
            bb_width_pct = (bb_upper - bb_lower) / bb_mid * 100 if bb_mid else 0
            if intended == "long":
                if current_price <= bb_lower:
                    signals.append(("Price at/below BB lower (mean-reversion long)", 18.0))
                elif current_price >= bb_upper:
                    signals.append(("Price above BB upper (breakout long)", 10.0))
            elif intended == "short":
                if current_price >= bb_upper:
                    signals.append(("Price at/above BB upper (mean-reversion short)", 18.0))
                elif current_price <= bb_lower:
                    signals.append(("Price below BB lower (breakout short)", 10.0))
            notes.append(f"BB width {bb_width_pct:.1f}%")

        # ── VWAP ─────────────────────────────────────────────────────────────
        if vwap is not None and current_price > 0:
            above_vwap = current_price > vwap
            if intended == "long" and above_vwap:
                signals.append(("Price above VWAP (bullish bias)", 12.0))
            elif intended == "long" and not above_vwap:
                signals.append(("Price below VWAP (counter-trend long)", -8.0))
            elif intended == "short" and not above_vwap:
                signals.append(("Price below VWAP (bearish bias)", 12.0))
            elif intended == "short" and above_vwap:
                signals.append(("Price above VWAP (counter-trend short)", -8.0))

        # ── Stochastic ───────────────────────────────────────────────────────
        if stoch_k is not None:
            if intended == "long" and stoch_k < 25:
                signals.append(("Stochastic oversold <25", 12.0))
            elif intended == "short" and stoch_k > 75:
                signals.append(("Stochastic overbought >75", 12.0))
            elif intended == "long" and stoch_k > 80:
                signals.append(("Stochastic overbought (risky long)", -8.0))

        # ── CCI ──────────────────────────────────────────────────────────────
        if cci is not None:
            if intended == "long" and cci < -100:
                signals.append(("CCI oversold <-100", 10.0))
            elif intended == "short" and cci > 100:
                signals.append(("CCI overbought >100", 10.0))

        # ── Volume spike ─────────────────────────────────────────────────────
        if vol_spike:
            signals.append(("Volume spike (2.5×+ average)", 15.0))
            notes.append("Volume spike detected — increased conviction")
        else:
            signals.append(("No volume spike", -5.0))

        # ── Support/Resistance ───────────────────────────────────────────────
        if sr:
            if intended == "long" and sr.get("at_support"):
                signals.append(("Price at support level", 20.0))
                notes.append(f"Support: {sr['support']:.4f}")
            elif intended == "short" and sr.get("at_resistance"):
                signals.append(("Price at resistance level", 20.0))
                notes.append(f"Resistance: {sr['resistance']:.4f}")
            elif intended == "long" and sr.get("at_resistance"):
                signals.append(("Price at resistance (risky long)", -15.0))
                flags.append("near_resistance_long")
            elif intended == "short" and sr.get("at_support"):
                signals.append(("Price at support (risky short)", -15.0))
                flags.append("near_support_short")

        # ── Market structure ─────────────────────────────────────────────────
        if structure:
            ms = structure.get("structure", "")
            if intended == "long" and ms == "bullish":
                signals.append(("Market structure: HH+HL (bullish)", 20.0))
            elif intended == "short" and ms == "bearish":
                signals.append(("Market structure: LL+LH (bearish)", 20.0))
            elif intended == "long" and ms == "bearish":
                signals.append(("Market structure bearish vs long intent", -20.0))
                flags.append("counter_trend")
            elif intended == "short" and ms == "bullish":
                signals.append(("Market structure bullish vs short intent", -20.0))
                flags.append("counter_trend")
            elif ms == "consolidation":
                signals.append(("Market consolidating (lower conviction)", -5.0))

        # ── Intraday 5m MACD/RSI confirmation ────────────────────────────────
        if rsi_5m is not None:
            if intended == "long" and rsi_5m < 40:
                signals.append(("5m RSI oversold (intraday dip)", 10.0))
            elif intended == "short" and rsi_5m > 60:
                signals.append(("5m RSI elevated (intraday peak)", 10.0))

        if macd_5m is not None:
            if intended == "long" and macd_5m > 0:
                signals.append(("5m MACD bullish (intraday alignment)", 8.0))
            elif intended == "short" and macd_5m < 0:
                signals.append(("5m MACD bearish (intraday alignment)", 8.0))
            elif (intended == "long" and macd_5m < 0) or (intended == "short" and macd_5m > 0):
                signals.append(("5m MACD counter to direction", -5.0))

        # ── Aggregate ────────────────────────────────────────────────────────
        total = sum(v for _, v in signals)
        score = max(-100.0, min(100.0, total))
        confidence = min(0.92, 0.35 + len([v for _, v in signals if v > 0]) * 0.06)

        decision = _direction_to_decision(intended, score)

        signal_text = "; ".join(f"{n}({v:+.0f})" for n, v in signals)
        log.info(
            "technical_analysis.scored",
            symbol=signal.symbol,
            direction=intended,
            score=round(score, 1),
            decision=decision.value,
            signals_count=len(signals),
            rsi=round(rsi, 1) if rsi else None,
            macd_hist=round(macd_hist, 6) if macd_hist else None,
            structure=structure.get("structure") if structure else None,
            vol_spike=vol_spike,
        )

        return self._make_result(
            decision=decision,
            score=score,
            confidence=confidence,
            reasoning=(
                f"Technical analysis ({intended}): {signal_text}"
                + (f" | Notes: {', '.join(notes)}" if notes else "")
            ),
            output={
                "rsi": rsi,
                "rsi_5m": rsi_5m,
                "ema_9": ema_9,
                "ema_21": ema_21,
                "ema_50": ema_50,
                "sma_20": sma_20,
                "sma_50": sma_50,
                "macd_line": macd_line,
                "macd_signal": macd_sig,
                "macd_hist": macd_hist,
                "macd_hist_5m": macd_5m,
                "bb_upper": bb_upper,
                "bb_mid": bb_mid,
                "bb_lower": bb_lower,
                "vwap": vwap,
                "stochastic_k": stoch_k,
                "cci": cci,
                "atr": atr,
                "volume_spike": vol_spike,
                "support_resistance": sr,
                "market_structure": structure,
                "current_price": current_price,
                "signals_breakdown": dict(signals),
            },
            risk_flags=flags,
        )


class PriceActionAgent(BaseAgent):
    """
    Market structure + trend + support/resistance price-action analysis.
    Higher-high / lower-low structure detection, EMA trend, position-in-range,
    momentum confirmation, and multi-timeframe structure alignment.
    """

    async def _execute(self, state: "PipelineState") -> AgentOutputResult:
        signal = state["signal"]
        intended = _get_direction(state)
        snapshots = _get_snapshots(state)

        if len(snapshots) < 5:
            return self._make_result(
                decision=AgentDecision.WAIT,
                score=0.0,
                confidence=0.1,
                reasoning="Insufficient history for price action analysis.",
            )

        closes  = extract_closes(snapshots)
        highs   = extract_highs(snapshots)
        lows    = extract_lows(snapshots)

        trend        = ind.detect_trend(closes, short=20, long=50)
        momentum_pct = ind.price_momentum(closes, lookback=5)
        momentum_3   = ind.price_momentum(closes, lookback=3)
        structure    = ind.detect_higher_highs_lower_lows(highs, lows, lookback=5)
        sr           = ind.detect_support_resistance(closes, lows, highs, lookback=30)

        # Position in recent range
        recent_high = max(highs[-20:]) if len(highs) >= 20 else highs[-1]
        recent_low  = min(lows[-20:])  if len(lows)  >= 20 else lows[-1]
        current     = closes[-1]
        range_size  = recent_high - recent_low
        position_in_range = (current - recent_low) / range_size if range_size > 0 else 0.5

        score = 0.0
        notes: list[str] = []
        flags: list[str] = []

        # ── EMA trend alignment ───────────────────────────────────────────────
        if trend == "uptrend" and intended == "long":
            score += 30.0
            notes.append("EMA uptrend aligns with long")
        elif trend == "downtrend" and intended == "short":
            score += 30.0
            notes.append("EMA downtrend aligns with short")
        elif trend == "sideways":
            score += 3.0
            notes.append("Sideways market — reduced conviction")
        elif trend is not None:
            score -= 25.0
            notes.append(f"EMA trend ({trend}) opposes signal ({intended})")
            flags.append("trend_opposition")

        # ── Market structure (HH/HL or LL/LH) ────────────────────────────────
        ms = structure.get("structure", "") if structure else ""
        if intended == "long":
            if ms == "bullish":
                score += 25.0
                notes.append("Bullish structure: HH + HL")
            elif ms == "bearish":
                score -= 20.0
                notes.append("Bearish structure: LL + LH (counter-trend long)")
                flags.append("counter_trend")
            elif ms == "consolidation":
                score += 2.0
                notes.append("Consolidating — breakout long possible")
        elif intended == "short":
            if ms == "bearish":
                score += 25.0
                notes.append("Bearish structure: LL + LH")
            elif ms == "bullish":
                score -= 20.0
                notes.append("Bullish structure: HH + HL (counter-trend short)")
                flags.append("counter_trend")

        # ── Support/Resistance position ───────────────────────────────────────
        if sr:
            if intended == "long":
                if sr.get("at_support"):
                    score += 22.0
                    notes.append(f"At support {sr['support']:.4f} — ideal long entry")
                elif sr.get("at_resistance"):
                    score -= 15.0
                    notes.append(f"At resistance {sr['resistance']:.4f} — risky long")
                    flags.append("near_resistance_long")
            elif intended == "short":
                if sr.get("at_resistance"):
                    score += 22.0
                    notes.append(f"At resistance {sr['resistance']:.4f} — ideal short entry")
                elif sr.get("at_support"):
                    score -= 15.0
                    notes.append(f"At support {sr['support']:.4f} — risky short")
                    flags.append("near_support_short")

        # ── Position in range ─────────────────────────────────────────────────
        if intended == "long":
            if position_in_range < 0.30:
                score += 15.0
                notes.append("Price near range low — good long zone")
            elif position_in_range > 0.85:
                score -= 18.0
                notes.append("Price near range high — stretched long")
                flags.append("late_long_entry")
        elif intended == "short":
            if position_in_range > 0.70:
                score += 15.0
                notes.append("Price near range high — good short zone")
            elif position_in_range < 0.15:
                score -= 18.0
                notes.append("Price near range low — stretched short")

        # ── Momentum confirmation ─────────────────────────────────────────────
        for mom, label in [(momentum_pct, "5-bar"), (momentum_3, "3-bar")]:
            if mom is not None:
                if intended == "long" and mom > 0.05:
                    score += 8.0
                elif intended == "short" and mom < -0.05:
                    score += 8.0
                elif abs(mom) > 2.0:
                    if (intended == "long" and mom < 0) or (intended == "short" and mom > 0):
                        score -= 8.0
                        flags.append("opposing_price_momentum")

        score = max(-100.0, min(100.0, score))
        confidence = 0.65 if trend and ms else 0.40

        return self._make_result(
            decision=_direction_to_decision(intended, score),
            score=score,
            confidence=confidence,
            reasoning="; ".join(notes) or "Price action analysis complete.",
            output={
                "trend":              trend,
                "market_structure":   ms,
                "position_in_range":  round(position_in_range, 3),
                "recent_high":        recent_high,
                "recent_low":         recent_low,
                "current_price":      current,
                "momentum_5bar_pct":  momentum_pct,
                "momentum_3bar_pct":  momentum_3,
                "support":            sr.get("support") if sr else None,
                "resistance":         sr.get("resistance") if sr else None,
                "at_support":         sr.get("at_support") if sr else False,
                "at_resistance":      sr.get("at_resistance") if sr else False,
            },
            risk_flags=flags,
        )


class MomentumAgent(BaseAgent):
    """
    Volume and price momentum analysis.
    Strong volume-backed moves score higher; low-volume moves score lower.
    """

    async def _execute(self, state: "PipelineState") -> AgentOutputResult:
        signal = state["signal"]
        intended = _get_direction(state)
        snapshots = _get_snapshots(state)

        if len(snapshots) < 10:
            return self._make_result(
                decision=AgentDecision.WAIT,
                score=0.0,
                confidence=0.1,
                reasoning="Insufficient history for momentum analysis.",
            )

        closes = extract_closes(snapshots)
        volumes = extract_volumes(snapshots)

        price_mom = ind.price_momentum(closes, lookback=5)
        vol_ratio = ind.volume_momentum(volumes, lookback=5)

        score = 0.0
        notes: list[str] = []
        flags: list[str] = []

        # ── Price momentum ────────────────────────────────────────────────────
        if price_mom is not None:
            if intended == "long" and price_mom > 0:
                score += min(30.0, price_mom * 3)
                notes.append(f"Positive price momentum +{price_mom:.2f}%")
            elif intended == "short" and price_mom < 0:
                score += min(30.0, abs(price_mom) * 3)
                notes.append(f"Negative price momentum {price_mom:.2f}%")
            elif intended == "long" and price_mom < -2:
                score -= 25.0
                notes.append(f"Opposing price momentum {price_mom:.2f}%")
                flags.append("opposing_price_momentum")
            elif intended == "short" and price_mom > 2:
                score -= 25.0
                flags.append("opposing_price_momentum")

        # ── Volume confirmation ───────────────────────────────────────────────
        if vol_ratio is not None:
            if vol_ratio >= 1.5:
                score += 25.0
                notes.append(f"Strong volume confirmation ({vol_ratio:.1f}x avg)")
            elif vol_ratio >= 1.0:
                score += 10.0
                notes.append(f"Average volume ({vol_ratio:.1f}x)")
            else:
                score -= 15.0
                notes.append(f"Weak volume ({vol_ratio:.1f}x avg)")
                flags.append("low_volume")

        score = max(-100.0, min(100.0, score))
        confidence = 0.7 if vol_ratio is not None and price_mom is not None else 0.4

        return self._make_result(
            decision=_direction_to_decision(intended, score),
            score=score,
            confidence=confidence,
            reasoning="; ".join(notes) or "Momentum analysis complete.",
            output={
                "price_momentum_5bar_pct": price_mom,
                "volume_ratio_vs_avg": vol_ratio,
            },
            risk_flags=flags,
        )
