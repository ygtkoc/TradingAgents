"""
Risk category agents.
All risk agents have can_veto=True and will short-circuit the pipeline
if they detect conditions that make the trade unsafe.

Risk agents evaluate position sizing, portfolio exposure, drawdown limits,
and overall trade viability from a risk management perspective.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from src.agents.base import BaseAgent
from src.config import settings
from src.db.models import AgentDecision, AgentOutputResult
from src.logging_config import get_logger
from src.services import indicators as ind
from src.services.market_data import extract_closes, extract_highs, extract_lows
from src.services.reward_plan import build_reward_plan, final_take_profit

if TYPE_CHECKING:
    from src.orchestration.state import PipelineState

log = get_logger(__name__)


def _get_snapshots(state: "PipelineState"):
    from src.db.models import MarketSnapshot
    return [MarketSnapshot.model_validate(s) for s in state.get("price_history", [])]


def _get_direction(state: "PipelineState") -> str:
    signal = state["signal"]
    return state.get("effective_direction") or signal.direction.value


# Strategy-specific minimum candle requirements.
# Scalping needs fewer bars (50); trend/momentum strategies need more for
# reliable ATR(14), RSI(14), and trend detection.
_CANDLES_REQUIRED_BY_STRATEGY: dict[str, int] = {
    "scalping":        50,
    "momentum":        100,
    "trend_following": 100,
    "mean_reversion":  100,
    "balanced":        100,
}
_CANDLES_MIN_LIVE = 15


def _candles_required_for_bot(bot_dict: dict) -> int:
    """Return strategy-specific candle threshold, respecting the DB column if present."""
    # 1. Prefer the DB column set by migration 0012.
    db_required = bot_dict.get("candles_required")
    if db_required and int(db_required) > 0:
        return int(db_required)
    # 2. Fall back to strategy-based lookup.
    strategy = (
        bot_dict.get("strategy_type")
        or bot_dict.get("metadata", {}).get("strategy", "balanced")
    )
    return _CANDLES_REQUIRED_BY_STRATEGY.get(str(strategy), 100)


def _float_from(*values: object) -> float:
    for value in values:
        try:
            parsed = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed
    return 0.0


def _select_reward_r(
    *,
    max_reward_r: float,
    min_reward_r: float,
    risk_score: float,
    atr_pct: float,
    strategy: str,
) -> tuple[float, str, str]:
    """Heuristic reward selector used by RewardPlanAgent."""
    max_r = max(1.0, min(10.0, float(max_reward_r or 5.0)))
    min_r = max(0.5, min(max_r, float(min_reward_r or 1.5)))
    reward_range = max(0.0, max_r - min_r)

    # max_reward_r is a ceiling, not a target. Most normal trades should sit
    # inside the range; only unusually clean, low-volatility setups can approach
    # the user's configured maximum.
    risk_quality = max(0.0, min(1.0, (float(risk_score) - 35.0) / 60.0))
    base_r = min_r + reward_range * (0.20 + risk_quality * 0.55)

    if strategy in {"trend_following", "momentum"}:
        base_r += reward_range * 0.10
        profile = "runner"
    elif strategy == "scalping":
        base_r -= reward_range * 0.15
        profile = "conservative"
    else:
        profile = "balanced"

    if atr_pct >= 4.0:
        base_r -= reward_range * 0.20
    elif atr_pct >= 2.5:
        base_r -= reward_range * 0.10
    elif atr_pct <= 1.0 and risk_score >= 85:
        base_r += reward_range * 0.10

    exceptional_setup = (
        risk_score >= 92.0
        and atr_pct <= 1.2
        and strategy in {"trend_following", "momentum"}
    )
    if not exceptional_setup and reward_range >= 0.25:
        base_r = min(base_r, max_r - 0.25)

    selected = max(min_r, min(max_r, base_r))
    selected = round(selected * 4.0) / 4.0
    selected = max(min_r, min(max_r, selected))
    rationale = (
        f"strategy={strategy}, risk_score={risk_score:.1f}, atr_pct={atr_pct:.2f}; "
        f"selected {selected:.2f}R inside user ceiling {max_r:.2f}R."
    )
    return selected, profile, rationale


class RiskAuditorAgent(BaseAgent):
    """
    Evaluates the trade's risk/reward profile.
    Checks ATR-based stop distance, position sizing, and accumulated risk flags
    from upstream agents.

    can_veto=True — vetoes if accumulated risk is unacceptable.
    """

    async def _execute(self, state: "PipelineState") -> AgentOutputResult:
        signal = state["signal"]
        intended = _get_direction(state)
        snapshot_dict = state.get("market_snapshot")
        snapshots = _get_snapshots(state)
        bot_dict  = state.get("bot") or {}
        bot_mode  = bot_dict.get("mode", "paper")

        candles_available = len(snapshots)
        candles_required  = (
            _candles_required_for_bot(bot_dict) if bot_mode in ("paper", "shadow")
            else _CANDLES_MIN_LIVE
        )

        # ── Trust the autonomous engine's DB-persisted warmup verdict ──────────
        # The signal generator runs count_recent() over the full 7-day snapshot
        # window (which includes pre-fetched historical bars). If it has marked
        # the bot 'ready', the pipeline's 150-bar fetch is sufficient context
        # even if it's < candles_required, because ATR and RSI only need ~15-20
        # bars — the threshold is a pre-trade buffer, not a per-run limit.
        db_warmup_status = bot_dict.get("warmup_status", "pending")
        if db_warmup_status == "ready":
            # DB has confirmed enough history exists globally; treat the pipeline
            # fetch as sufficient for indicator computation.
            candles_available = max(candles_available, candles_required)

        log.info(
            "risk.history.available",
            symbol=signal.symbol,
            candles_available=candles_available,
            candles_required=candles_required,
            bot_mode=bot_mode,
            db_warmup_status=db_warmup_status,
            pipeline_bars_fetched=len(snapshots),
        )

        if not snapshot_dict:
            # No snapshot at all — always hard-veto regardless of mode.
            return self._safe_veto(
                reason="No market snapshot available. Cannot assess risk.",
                severity_flags=["risk_assessment_impossible"],
            )

        if candles_available < candles_required:
            if bot_mode in ("paper", "shadow"):
                # Paper/shadow: emit a soft non-veto WAIT so the pipeline
                # records the warmup reason without permanently blocking trades.
                # Setting risk_score=0 produces the maximum risk_deduction in
                # the aggregator (30 pts) which keeps the final score below the
                # open-trade threshold even if analysis agents are bullish.
                state["warming_up"] = True
                state["risk_score"] = 0.0
                estimated_minutes = candles_required - candles_available
                log.info(
                    "risk.warmup.wait",
                    symbol=signal.symbol,
                    candles_available=candles_available,
                    candles_required=candles_required,
                    estimated_ready_in_minutes=estimated_minutes,
                )
                return self._make_result(
                    decision=AgentDecision.WAIT,
                    score=-50.0,
                    confidence=0.1,
                    reasoning=(
                        f"Warming up: {candles_available}/{candles_required} historical "
                        f"candles available for {signal.symbol}. "
                        f"Risk assessment requires {candles_required} bars to compute "
                        "reliable ATR and RSI indicators. "
                        "Paper trading will resume automatically once history is sufficient."
                    ),
                    output={
                        "candles_available": candles_available,
                        "candles_required": candles_required,
                        "warming_up": True,
                        "insufficient_history": True,
                        "rejection_reason": "insufficient_history_warming_up",
                        "estimated_ready_in_minutes": estimated_minutes,
                    },
                    risk_flags=["insufficient_history"],
                    recommendations=[
                        f"Wait {estimated_minutes} more closed "
                        f"{settings.market_data_kline_interval} candles.",
                        "The signal generator will retry automatically on its next tick.",
                    ],
                )
            else:
                # Live mode: hard-veto — never trade without sufficient history.
                return self._safe_veto(
                    reason=(
                        f"Insufficient market data: {candles_available}/{candles_required} bars. "
                        "Cannot size position safely for live trading."
                    ),
                    severity_flags=["risk_assessment_impossible"],
                )

        from src.db.models import MarketSnapshot
        snapshot = MarketSnapshot.model_validate(snapshot_dict)
        closes = extract_closes(snapshots)
        highs = extract_highs(snapshots)
        lows = extract_lows(snapshots)
        current_price = closes[-1]

        risk_score = 100.0  # Start with clean score, deduct for each risk
        findings: list[str] = []
        flags: list[str] = []

        # ── ATR-based stop distance ───────────────────────────────────────────
        atr = ind.compute_atr(highs, lows, closes, period=14)
        if atr is None:
            risk_score -= 20.0
            findings.append("ATR unavailable — cannot compute stop distance")
            flags.append("no_atr")
            log.warning("risk.atr.unavailable", symbol=signal.symbol, candles=candles_available)
        else:
            atr_pct = (atr / current_price) * 100 if current_price > 0 else 0.0
            stop_distance_2x = atr_pct * 2  # 2 ATR stop (standard)

            log.info(
                "risk.atr.calculated",
                symbol=signal.symbol,
                atr=round(atr, 8),
                atr_pct=round(atr_pct, 4),
                current_price=round(current_price, 8),
                stop_distance_2x_pct=round(stop_distance_2x, 4),
            )

            if atr_pct > 5.0:
                risk_score -= 30.0
                findings.append(f"ATR {atr_pct:.2f}% — very high volatility, wide stop required")
                flags.append("high_volatility")
            elif atr_pct > 2.5:
                risk_score -= 10.0
                findings.append(f"ATR {atr_pct:.2f}% — elevated volatility")
            else:
                findings.append(f"ATR {atr_pct:.2f}% — manageable volatility")

            state["atr"] = atr
            state["atr_pct"] = atr_pct
            state["suggested_stop_pct"] = stop_distance_2x

        # ── Accumulated risk flags from upstream agents ───────────────────────
        all_risk_flags: list[str] = []
        for result in state.get("agent_results", []):
            all_risk_flags.extend(result.get("risk_flags", []))

        critical_flags = {
            "extreme_spread", "extreme_volume_spike", "potential_pump",
            "low_volume_spike", "ohlcv_anomaly", "manipulated_market",
        }
        warning_flags = {
            "high_spread", "volume_spike", "price_volume_divergence",
            "momentum_exhaustion", "counter_trend", "opposing_price_momentum",
        }

        critical_found = [f for f in all_risk_flags if f in critical_flags]
        warning_found = [f for f in all_risk_flags if f in warning_flags]

        if critical_found:
            risk_score -= len(critical_found) * 25.0
            findings.append(f"Critical risk flags: {', '.join(critical_found)}")
            flags.extend(critical_found)

        if warning_found:
            risk_score -= len(warning_found) * 10.0
            findings.append(f"Warning flags: {', '.join(warning_found)}")
            flags.extend(warning_found)

        # ── Manipulation score from state ─────────────────────────────────────
        manipulation_penalty = state.get("manipulation_score_penalty", 0.0)
        if manipulation_penalty > 0:
            risk_score -= manipulation_penalty * 0.3
            findings.append(f"Manipulation penalty applied: {manipulation_penalty:.1f}")

        # ── Data quality score ────────────────────────────────────────────────
        data_quality = state.get("data_quality_score", 100.0)
        if data_quality < 60.0:
            risk_score -= (60.0 - data_quality) * 0.5
            findings.append(f"Data quality concern: {data_quality:.1f}/100")

        # ── RSI risk check ────────────────────────────────────────────────────
        rsi = ind.compute_rsi(closes, 14)
        if rsi is not None:
            if intended == "long" and rsi > 75:
                risk_score -= 20.0
                findings.append(f"RSI {rsi:.1f} — entering long in extreme overbought territory")
                flags.append("extreme_overbought_long")
            elif intended == "short" and rsi < 25:
                risk_score -= 20.0
                findings.append(f"RSI {rsi:.1f} — entering short in extreme oversold territory")
                flags.append("extreme_oversold_short")

        # ── Clamp and veto decision ───────────────────────────────────────────
        risk_score = max(0.0, min(100.0, risk_score))
        state["risk_score"] = risk_score

        # Hard veto: critical market conditions
        if critical_found:
            return self._safe_veto(
                reason=(
                    f"Critical risk flags block trade execution: {', '.join(critical_found)}. "
                    f"Risk score: {risk_score:.1f}/100"
                ),
                severity_flags=flags,
            )

        # Soft veto: cumulative risk too high
        if risk_score < 30.0:
            return self._safe_veto(
                reason=(
                    f"Cumulative risk score {risk_score:.1f}/100 below safe threshold (30). "
                    + "; ".join(findings)
                ),
                severity_flags=flags,
            )

        # Convert to centred score for aggregation: 100 → +50, 50 → 0, 0 → -50
        aggregation_score = (risk_score - 50.0)
        confidence = 0.85 if atr is not None else 0.5

        # Compute rough position sizing estimate for logs
        risk_model = bot_dict.get("risk_model", "percentage")
        risk_value = float(bot_dict.get("risk_value") or bot_dict.get("risk_per_trade_pct") or 2.0)
        log.info(
            "risk.position_size.calculated",
            symbol=signal.symbol,
            risk_score=round(risk_score, 2),
            aggregation_score=round(aggregation_score, 2),
            risk_model=risk_model,
            risk_value=risk_value,
            atr_pct=round(state.get("atr_pct") or 0.0, 4),
            suggested_stop_pct=round(state.get("suggested_stop_pct") or 0.0, 4),
            candles_used=candles_available,
        )

        return self._make_result(
            decision=AgentDecision.WAIT,  # Risk agent does not set direction
            score=aggregation_score,
            confidence=confidence,
            reasoning="; ".join(findings) or "Risk assessment passed.",
            output={
                "risk_score": risk_score,
                "atr": atr,
                "atr_pct": state.get("atr_pct"),
                "suggested_stop_pct": state.get("suggested_stop_pct"),
                "critical_flags": critical_found,
                "warning_flags": warning_found,
                "manipulation_penalty": manipulation_penalty,
                "data_quality_score": data_quality,
                "candles_available": candles_available,
                "candles_required": candles_required,
                "warming_up": False,
            },
            risk_flags=flags,
        )


class RewardPlanAgent(BaseAgent):
    """
    Builds an automatic per-trade reward/R and scaled TP plan.

    This is the risk-management "AI controller" for exits: it caps reward by
    user max_reward_r, adapts selected R to volatility/risk score/strategy, and
    writes TP1/TP2/TP3 levels into pipeline state for execution.
    """

    async def _execute(self, state: "PipelineState") -> AgentOutputResult:
        signal = state["signal"]
        intended = _get_direction(state)
        snapshot_dict = state.get("market_snapshot")
        bot_dict = state.get("bot") or {}
        user_settings = state.get("user_settings") or {}

        if not snapshot_dict:
            return self._safe_veto(
                reason="Reward planner cannot run without a market snapshot.",
                severity_flags=["reward_plan_impossible"],
            )

        current_price = float(snapshot_dict.get("close_price") or 0.0)
        if current_price <= 0:
            return self._safe_veto(
                reason="Reward planner cannot run with invalid entry price.",
                severity_flags=["reward_plan_impossible"],
            )

        metadata = bot_dict.get("metadata") or {}
        atr_pct = float(state.get("atr_pct") or 0.0)
        stop_pct = float(
            metadata.get("stop_loss_pct")
            or state.get("suggested_stop_pct")
            or max(2.0, atr_pct * 2.0)
        )
        stop_distance = current_price * stop_pct / 100.0
        if stop_distance <= 0:
            return self._safe_veto(
                reason="Reward planner computed a zero stop distance.",
                severity_flags=["reward_plan_impossible"],
            )

        direction = "short" if intended == "short" else "long"
        stop_loss = current_price + stop_distance if direction == "short" else current_price - stop_distance

        max_reward_r = _float_from(
            user_settings.get("max_reward_r"),
            metadata.get("max_reward_r"),
            5.0,
        )
        min_reward_r = _float_from(
            user_settings.get("min_reward_r"),
            metadata.get("min_reward_r"),
            1.5,
        )

        risk_score = float(state.get("risk_score") or 50.0)
        strategy = str(bot_dict.get("strategy_type") or metadata.get("strategy") or "balanced")
        requested_r, profile, rationale = _select_reward_r(
            max_reward_r=max_reward_r,
            min_reward_r=min_reward_r,
            risk_score=risk_score,
            atr_pct=atr_pct,
            strategy=strategy,
        )

        if requested_r < min_reward_r:
            return self._safe_veto(
                reason=(
                    f"Reward potential {requested_r:.2f}R is below minimum "
                    f"{min_reward_r:.2f}R for {signal.symbol}."
                ),
                severity_flags=["insufficient_reward_potential"],
            )

        plan = build_reward_plan(
            entry_price=current_price,
            stop_loss=stop_loss,
            direction=direction,
            requested_reward_r=requested_r,
            max_reward_r=max_reward_r,
            min_reward_r=min_reward_r,
            close_profile=profile,
            rationale=rationale,
            confidence=0.82,
        )
        if not plan:
            return self._safe_veto(
                reason="Reward planner failed to build a valid TP plan.",
                severity_flags=["reward_plan_impossible"],
            )

        take_profit = final_take_profit(plan)
        state["reward_plan"] = plan
        state["selected_reward_r"] = plan["selected_reward_r"]
        state["max_reward_r"] = max_reward_r
        state["min_reward_r"] = min_reward_r

        return self._make_result(
            decision=AgentDecision.WAIT,
            score=15.0,
            confidence=0.82,
            reasoning=(
                f"Reward plan selected {plan['selected_reward_r']:.2f}R "
                f"(max {max_reward_r:.2f}R). {rationale}"
            ),
            output={
                "entry_price": current_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "risk_reward_ratio": plan["selected_reward_r"],
                "reward_plan": plan,
                "tp_plan": plan["levels"],
                "max_reward_r": max_reward_r,
                "min_reward_r": min_reward_r,
            },
            recommendations=[
                "Use TP1/TP2/TP3 scaled exits instead of a single full take-profit.",
                "Move stop to breakeven after TP1 and protect TP1 area after TP2.",
            ],
        )


class ChiefRiskOfficerAgent(BaseAgent):
    """
    Final risk gate before trade decision.
    Reviews the complete picture: all agent scores, all flags, bot-level
    risk settings (max open trades, daily loss limits, position limits).

    can_veto=True — this is the last line of risk defense.
    """

    async def _execute(self, state: "PipelineState") -> AgentOutputResult:
        signal = state["signal"]
        bot_dict = state.get("bot")
        config_dict = state.get("bot_config")
        user_settings_dict = state.get("user_settings")
        open_trade_count = state.get("open_trade_count", 0)

        if not bot_dict:
            return self._safe_veto(
                reason="Bot missing from state — cannot perform CRO risk check.",
                severity_flags=["missing_bot_context"],
            )

        from src.db.models import Bot, BotConfig, UserSettings  # noqa: F401
        bot = Bot.model_validate(bot_dict)
        config = (
            BotConfig.model_validate(config_dict)
            if config_dict
            else BotConfig(
                id=f"synthetic-{bot.id}",
                bot_id=bot.id,
                user_id=bot.user_id,
                version=0,
                config={},
                is_active=True,
            )
        )
        user_settings = (
            UserSettings.model_validate(user_settings_dict) if user_settings_dict else None
        )

        veto_reasons: list[str] = []
        warnings: list[str] = []
        flags: list[str] = []

        # ── Bot status check ──────────────────────────────────────────────────
        if bot.status.value not in ("active",):
            return self._safe_veto(
                reason=f"Bot {bot.id} is not active (status={bot.status.value}). Blocking trade.",
                severity_flags=["bot_not_active"],
            )

        # ── Live trading permission check ─────────────────────────────────────
        if bot.mode.value == "live" and not bot.real_trading_enabled:
            return self._safe_veto(
                reason=f"Bot {bot.id} is in live mode but real_trading_enabled=False.",
                severity_flags=["live_trading_disabled"],
            )

        # ── Max concurrent trades ─────────────────────────────────────────────
        # Bot-level setting takes precedence; BotConfig.config dict may override
        max_concurrent = (
            config.config.get("max_concurrent_trades")
            or bot.max_open_positions
            or 3
        )
        if open_trade_count >= max_concurrent:
            return self._safe_veto(
                reason=(
                    f"Open trade count ({open_trade_count}) >= max_concurrent_trades ({max_concurrent}). "
                    "Position limit reached."
                ),
                severity_flags=["position_limit_reached"],
            )

        # ── Max position size check ───────────────────────────────────────────
        max_pos_pct = (
            config.config.get("max_position_size_pct")
            or bot.max_position_size_pct
            or 10.0
        )
        if max_pos_pct > 25.0:
            warnings.append(f"max_position_size_pct={max_pos_pct:.1f}% is very high — risk of overexposure")
            flags.append("high_position_size_config")

        # ── Risk score from RiskAuditorAgent ─────────────────────────────────
        risk_score = state.get("risk_score", 50.0)
        if risk_score < 40.0:
            veto_reasons.append(f"Upstream risk score {risk_score:.1f}/100 below CRO threshold (40)")
            flags.append("low_risk_score")

        # ── Accumulated flags review ──────────────────────────────────────────
        manipulation_flags = state.get("manipulation_flags", [])
        high_severity_manipulation = {
            "extreme_spread", "potential_pump", "low_volume_spike",
            "ohlcv_anomaly", "extreme_volume_spike",
        }
        active_manipulation = [f for f in manipulation_flags if f in high_severity_manipulation]
        if active_manipulation:
            veto_reasons.append(
                f"Active manipulation signals not cleared: {', '.join(active_manipulation)}"
            )
            flags.extend(active_manipulation)

        # ── User-level trading restrictions ───────────────────────────────────
        if user_settings:
            # For live bots, check real_trading_enabled; paper bots use paper_trading_enabled
            live = bot.mode.value == "live"
            enabled = (
                user_settings.real_trading_enabled if live else user_settings.paper_trading_enabled
            )
            if not enabled:
                mode_label = "live" if live else "paper"
                return self._safe_veto(
                    reason=f"User has disabled {mode_label} trading in account settings.",
                    severity_flags=["user_trading_disabled"],
                )

        # ── Dry run override ──────────────────────────────────────────────────
        if settings.dry_run:
            warnings.append("DRY RUN MODE — trade decision will be recorded but not executed")

        # ── Apply veto if any hard failures ──────────────────────────────────
        if veto_reasons:
            return self._safe_veto(
                reason="CRO veto: " + "; ".join(veto_reasons),
                severity_flags=flags,
            )

        # ── All clear ────────────────────────────────────────────────────────
        cro_score = max(0.0, risk_score - len(warnings) * 5.0)
        aggregation_score = (cro_score - 50.0)

        return self._make_result(
            decision=AgentDecision.WAIT,
            score=aggregation_score,
            confidence=0.9,
            reasoning=(
                "CRO check passed. "
                + (f"Warnings: {'; '.join(warnings)}" if warnings else "No warnings.")
            ),
            output={
                "bot_status": bot.status.value,
                "bot_mode": bot.mode.value,
                "open_trade_count": open_trade_count,
                "max_concurrent_trades": max_concurrent,
                "max_position_size_pct": max_pos_pct,
                "risk_score": risk_score,
                "manipulation_flags": manipulation_flags,
                "warnings": warnings,
                "dry_run": settings.dry_run,
            },
            risk_flags=flags,
        )
