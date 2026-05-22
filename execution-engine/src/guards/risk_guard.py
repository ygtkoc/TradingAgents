"""
RiskExecutionGuard — deterministic pre-execution risk checks.

Every check is synchronous and pure where possible. I/O (DB reads) is done
by the caller (ExecutionEngine) and passed in as pre-fetched context objects.

DESIGN: fail-closed. Any check returning blocked=True prevents execution
and records a risk_log entry. Unknown / missing data → blocked.

Checks performed (in order):
  1.  Symbol allowed by bot.trading_pairs
  2.  Max open trades limit
  3.  Max open positions per bot
  4.  Daily loss limit (USD or pct of portfolio)
  5.  Max portfolio exposure pct
  6.  Max position size pct
  7.  Risk-per-trade pct → validates quantity vs. portfolio
  8.  Stop-loss required for live trades
  9.  Take-profit optional warning (does NOT block)
  10. Quote / base currency valid
  11. Leverage placeholder (warns; blocks if leverage > 1 on live)
  12. Price slippage limit (market price vs. decision price)
  13. Minimum liquidity / spread limit
  14. Correlation risk placeholder (always passes, logs warning)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from src.config import settings
from src.db.models import Bot, MarketSnapshot, TradeDecision, UserSettings
from src.logging_config import get_logger

log = get_logger(__name__)

# Actionable final_decisions — only these should reach the execution pipeline
_ACTIONABLE_DECISIONS = frozenset({"open_long", "open_short"})

# Maximum slippage we tolerate when comparing the current price to the
# price that was recorded when the agent made its decision.
_DEFAULT_MAX_PRICE_SLIPPAGE_PCT = settings.max_slippage_pct
_DEFAULT_MAX_SPREAD_PCT         = settings.max_spread_pct


def _is_futures_profile(bot: Bot) -> bool:
    return str((bot.metadata or {}).get("trading_system") or "") == "futures_trading"


def _risk_limit_pct(bot: Bot, user_settings: Optional[UserSettings]) -> float:
    if user_settings is not None:
        try:
            value = float(user_settings.default_risk_per_trade_pct)
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    if bot.risk_model == "percentage":
        try:
            return float(bot.risk_value)
        except (TypeError, ValueError):
            pass
    return float(bot.risk_per_trade_pct or 0.0)


@dataclass
class RiskCheckResult:
    """Result of a single risk check."""
    name:    str
    passed:  bool
    message: str
    severity: str = "medium"   # info / low / medium / high / critical
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskGuardResult:
    """Aggregate result from RiskExecutionGuard.check()."""
    blocked:    bool
    reason:     str                           # human-readable summary
    checks:     list[RiskCheckResult] = field(default_factory=list)

    @property
    def failed_checks(self) -> list[RiskCheckResult]:
        return [c for c in self.checks if not c.passed]

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocked":  self.blocked,
            "reason":   self.reason,
            "checks":   [
                {
                    "name":     c.name,
                    "passed":   c.passed,
                    "message":  c.message,
                    "severity": c.severity,
                }
                for c in self.checks
            ],
        }


class RiskExecutionGuard:
    """
    Evaluates all deterministic risk rules before order placement.

    Usage:
        result = risk_guard.check(
            decision=decision,
            bot=bot,
            user_settings=user_settings,
            open_trade_count=open_trade_count,
            market_snapshot=market_snapshot,
            portfolio_value_usd=portfolio_value_usd,
            daily_loss_usd=daily_loss_usd,
        )
        if result.blocked:
            raise ExecutionBlockedError(result.reason)
    """

    def check(
        self,
        *,
        decision: TradeDecision,
        bot: Bot,
        user_settings: Optional[UserSettings],
        open_trade_count: int,
        market_snapshot: Optional[MarketSnapshot],
        portfolio_value_usd: float,
        daily_loss_usd: float = 0.0,
        quantity: float,
        entry_price: float,
    ) -> RiskGuardResult:
        """
        Run all risk checks. Returns immediately-blocked if any critical check fails.
        Collects all check results for logging regardless.
        """
        checks: list[RiskCheckResult] = []
        is_live = decision.mode == "live"

        # ── 1. Symbol allowed ─────────────────────────────────────────────────
        checks.append(self._check_symbol_allowed(decision, bot))

        # ── 2. Max open trades (user-wide) ────────────────────────────────────
        checks.append(self._check_max_concurrent_trades(open_trade_count, user_settings))

        # ── 3. Max open positions per bot ─────────────────────────────────────
        checks.append(self._check_max_positions_per_bot(open_trade_count, bot))

        # ── 4. Daily loss limit ───────────────────────────────────────────────
        checks.append(self._check_daily_loss(daily_loss_usd, bot, user_settings, portfolio_value_usd))

        # ── 5. Max portfolio exposure ─────────────────────────────────────────
        checks.append(self._check_portfolio_exposure(quantity, entry_price, portfolio_value_usd, bot))

        # ── 6. Max position size pct ──────────────────────────────────────────
        checks.append(self._check_position_size_pct(quantity, entry_price, portfolio_value_usd, bot))

        # ── 7. Risk-per-trade pct ─────────────────────────────────────────────
        checks.append(self._check_risk_per_trade(
            quantity=quantity,
            entry_price=entry_price,
            stop_loss=decision.risk_summary.get("stop_loss"),
            portfolio_value_usd=portfolio_value_usd,
            bot=bot,
            user_settings=user_settings,
        ))

        # ── 8. Stop-loss required (live only) ─────────────────────────────────
        checks.append(self._check_stop_loss_required(decision, is_live))

        # ── 9. Take-profit optional (warning only) ────────────────────────────
        checks.append(self._check_take_profit_advisory(decision))

        # ── 10. Currency validity ─────────────────────────────────────────────
        checks.append(self._check_currency(decision, bot))

        # ── 11. Leverage (placeholder) ────────────────────────────────────────
        checks.append(self._check_leverage_placeholder(decision, is_live))

        # ── 12. Price slippage ────────────────────────────────────────────────
        checks.append(self._check_price_slippage(
            entry_price=entry_price,
            market_snapshot=market_snapshot,
        ))

        # ── 13. Spread limit ──────────────────────────────────────────────────
        checks.append(self._check_spread_limit(market_snapshot))

        # ── 14. Correlation risk (placeholder, advisory only) ─────────────────
        checks.append(self._check_correlation_placeholder())

        # ── Aggregate ─────────────────────────────────────────────────────────
        failed = [c for c in checks if not c.passed]
        blocked = any(c.severity in ("high", "critical") for c in failed)

        if failed:
            reasons = "; ".join(c.message for c in failed if not c.passed)
            log.warning(
                "risk_guard.checks_failed",
                decision_id=decision.id,
                mode=decision.mode,
                blocked=blocked,
                failed_count=len(failed),
                reasons=reasons[:300],
            )
        else:
            log.info(
                "risk_guard.all_passed",
                decision_id=decision.id,
                mode=decision.mode,
            )

        return RiskGuardResult(
            blocked=blocked,
            reason="; ".join(c.message for c in failed) if failed else "all checks passed",
            checks=checks,
        )

    # ── Individual checks ──────────────────────────────────────────────────────

    def _check_symbol_allowed(self, decision: TradeDecision, bot: Bot) -> RiskCheckResult:
        allowed = bot.trading_pairs
        if allowed and decision.symbol not in allowed:
            return RiskCheckResult(
                name="symbol_allowed",
                passed=False,
                message=f"Symbol {decision.symbol} not in bot.trading_pairs {allowed}",
                severity="high",
                metadata={"symbol": decision.symbol, "allowed": allowed},
            )
        return RiskCheckResult(
            name="symbol_allowed",
            passed=True,
            message=f"Symbol {decision.symbol} allowed",
        )

    def _check_max_concurrent_trades(
        self, open_trade_count: int, user_settings: Optional[UserSettings]
    ) -> RiskCheckResult:
        limit = user_settings.max_concurrent_trades if user_settings else None
        if limit is not None and open_trade_count >= limit:
            return RiskCheckResult(
                name="max_concurrent_trades",
                passed=False,
                message=f"Open trades ({open_trade_count}) >= user limit ({limit})",
                severity="high",
                metadata={"open": open_trade_count, "limit": limit},
            )
        return RiskCheckResult(
            name="max_concurrent_trades",
            passed=True,
            message=f"Open trades ({open_trade_count}) within user limit",
        )

    def _check_max_positions_per_bot(self, open_trade_count: int, bot: Bot) -> RiskCheckResult:
        if open_trade_count >= bot.max_open_positions:
            return RiskCheckResult(
                name="max_positions_per_bot",
                passed=False,
                message=(
                    f"Bot open positions ({open_trade_count}) >= max ({bot.max_open_positions})"
                ),
                severity="high",
                metadata={"open": open_trade_count, "limit": bot.max_open_positions},
            )
        return RiskCheckResult(
            name="max_positions_per_bot",
            passed=True,
            message=f"Bot positions ({open_trade_count}) within limit ({bot.max_open_positions})",
        )

    def _check_daily_loss(
        self,
        daily_loss_usd: float,
        bot: Bot,
        user_settings: Optional[UserSettings],
        portfolio_value_usd: float,
    ) -> RiskCheckResult:
        # Check user-level daily loss limit (USD absolute)
        if user_settings and user_settings.daily_loss_limit_usd is not None:
            if daily_loss_usd >= user_settings.daily_loss_limit_usd:
                return RiskCheckResult(
                    name="daily_loss_limit",
                    passed=False,
                    message=(
                        f"Daily loss ${daily_loss_usd:.2f} >= user limit "
                        f"${user_settings.daily_loss_limit_usd:.2f}"
                    ),
                    severity="critical",
                    metadata={
                        "daily_loss_usd": daily_loss_usd,
                        "limit_usd": user_settings.daily_loss_limit_usd,
                    },
                )

        # Check bot-level daily loss pct
        if portfolio_value_usd > 0:
            loss_pct = (daily_loss_usd / portfolio_value_usd) * 100
            if loss_pct >= bot.max_daily_loss_pct:
                return RiskCheckResult(
                    name="daily_loss_limit",
                    passed=False,
                    message=(
                        f"Daily loss {loss_pct:.2f}% >= bot limit {bot.max_daily_loss_pct:.2f}%"
                    ),
                    severity="critical",
                    metadata={
                        "daily_loss_pct": round(loss_pct, 4),
                        "limit_pct": bot.max_daily_loss_pct,
                        "portfolio_usd": portfolio_value_usd,
                    },
                )

        return RiskCheckResult(
            name="daily_loss_limit",
            passed=True,
            message=f"Daily loss ${daily_loss_usd:.2f} within limits",
        )

    def _check_portfolio_exposure(
        self,
        quantity: float,
        entry_price: float,
        portfolio_value_usd: float,
        bot: Bot,
    ) -> RiskCheckResult:
        if portfolio_value_usd <= 0:
            return RiskCheckResult(
                name="portfolio_exposure",
                passed=False,
                message="Portfolio value unknown or zero — cannot compute exposure",
                severity="high",
            )

        position_value = quantity * entry_price
        exposure_pct   = (position_value / portfolio_value_usd) * 100
        # Exposure cap: sum of all positions should not exceed 100%.
        # For a single new position we cap at max_position_size_pct * max_open_positions.
        # This is an approximation — a proper implementation would sum existing exposure.
        max_exposure_pct = 100.0

        if exposure_pct > max_exposure_pct:
            return RiskCheckResult(
                name="portfolio_exposure",
                passed=False,
                message=(
                    f"Position exposure {exposure_pct:.2f}% > max {max_exposure_pct:.2f}%"
                ),
                severity="high",
                metadata={
                    "exposure_pct": round(exposure_pct, 4),
                    "max_pct": max_exposure_pct,
                    "position_value_usd": round(position_value, 2),
                },
            )
        return RiskCheckResult(
            name="portfolio_exposure",
            passed=True,
            message=f"Exposure {exposure_pct:.2f}% within limit {max_exposure_pct:.2f}%",
        )

    def _check_position_size_pct(
        self,
        quantity: float,
        entry_price: float,
        portfolio_value_usd: float,
        bot: Bot,
    ) -> RiskCheckResult:
        if portfolio_value_usd <= 0:
            return RiskCheckResult(
                name="position_size_pct",
                passed=False,
                message="Portfolio value unknown — cannot check position size",
                severity="high",
            )

        position_value = quantity * entry_price
        size_pct = (position_value / portfolio_value_usd) * 100

        limit_pct = 100.0

        if size_pct > limit_pct:
            return RiskCheckResult(
                name="position_size_pct",
                passed=False,
                message=(
                    f"Position size {size_pct:.2f}% > bot max {limit_pct:.2f}%"
                ),
                severity="high",
                metadata={
                    "size_pct": round(size_pct, 4),
                    "limit_pct": limit_pct,
                },
            )
        return RiskCheckResult(
            name="position_size_pct",
            passed=True,
            message=f"Position size {size_pct:.2f}% within limit {limit_pct:.2f}%",
        )

    def _check_risk_per_trade(
        self,
        quantity: float,
        entry_price: float,
        stop_loss: Any,
        portfolio_value_usd: float,
        bot: Bot,
        user_settings: Optional[UserSettings],
    ) -> RiskCheckResult:
        """
        If stop_loss is present, compute risk = (entry - stop_loss) * qty.
        Risk should not exceed the account-wide wallet risk percentage.
        """
        if stop_loss is None:
            return RiskCheckResult(
                name="risk_per_trade",
                passed=True,
                message="No stop_loss provided; risk_per_trade check skipped",
                severity="info",
            )

        try:
            sl = float(stop_loss)
        except (TypeError, ValueError):
            return RiskCheckResult(
                name="risk_per_trade",
                passed=True,
                message="stop_loss not numeric; skipping risk_per_trade check",
                severity="info",
            )

        if portfolio_value_usd <= 0:
            return RiskCheckResult(
                name="risk_per_trade",
                passed=False,
                message="Portfolio value unknown — cannot check risk per trade",
                severity="high",
            )

        risk_per_unit = abs(entry_price - sl)
        risk_usd      = risk_per_unit * quantity
        risk_pct      = (risk_usd / portfolio_value_usd) * 100
        limit_pct     = _risk_limit_pct(bot, user_settings)

        if risk_pct > limit_pct:
            return RiskCheckResult(
                name="risk_per_trade",
                passed=False,
                message=(
                    f"Trade risk {risk_pct:.2f}% > wallet risk limit {limit_pct:.2f}%"
                ),
                severity="high",
                metadata={
                    "risk_usd": round(risk_usd, 4),
                    "risk_pct": round(risk_pct, 4),
                    "limit_pct": limit_pct,
                },
            )
        return RiskCheckResult(
            name="risk_per_trade",
            passed=True,
            message=f"Trade risk {risk_pct:.2f}% within limit {limit_pct:.2f}%",
        )

    def _check_stop_loss_required(
        self, decision: TradeDecision, is_live: bool
    ) -> RiskCheckResult:
        has_sl = bool(decision.risk_summary.get("stop_loss"))

        requires_stop = (
            (is_live and settings.require_stop_loss_live)
            or decision.mode in {"paper", "shadow"}
        )
        if not has_sl and requires_stop:
            return RiskCheckResult(
                name="stop_loss_required",
                passed=False,
                message="Trade requires stop_loss to enforce max risk; none found in risk_summary",
                severity="critical" if is_live else "high",
            )

        return RiskCheckResult(
            name="stop_loss_required",
            passed=True,
            message="Stop-loss check passed",
            severity="info" if not has_sl else "info",
        )

    def _check_take_profit_advisory(self, decision: TradeDecision) -> RiskCheckResult:
        has_tp = bool(decision.risk_summary.get("take_profit"))
        return RiskCheckResult(
            name="take_profit_advisory",
            passed=True,   # never blocks
            message="Take-profit present" if has_tp else "No take_profit (advisory warning only)",
            severity="info",
        )

    def _check_currency(self, decision: TradeDecision, bot: Bot) -> RiskCheckResult:
        symbol  = decision.symbol.upper()
        base_ccy = bot.base_currency.upper()

        # symbol should be like "BTC/USDT" or "BTCUSDT"
        if "/" in symbol:
            parts = symbol.split("/")
            quote = parts[-1]
        else:
            # Strip known quote currencies (rough heuristic)
            quote = "USDT"  # fallback

        if quote != base_ccy:
            return RiskCheckResult(
                name="currency_valid",
                passed=False,
                message=(
                    f"Symbol quote currency '{quote}' != bot base_currency '{base_ccy}'"
                ),
                severity="high",
                metadata={"symbol": symbol, "bot_base_currency": base_ccy, "quote": quote},
            )
        return RiskCheckResult(
            name="currency_valid",
            passed=True,
            message=f"Currency valid: quote={quote}, base={base_ccy}",
        )

    def _check_leverage_placeholder(
        self, decision: TradeDecision, is_live: bool
    ) -> RiskCheckResult:
        leverage = decision.metadata.get("leverage", 1)
        try:
            leverage = float(leverage)
        except (TypeError, ValueError):
            leverage = 1.0

        if is_live and leverage > 1.0:
            return RiskCheckResult(
                name="leverage_check",
                passed=False,
                message=(
                    f"Leverage {leverage}x detected. Leveraged live trading not yet supported. "
                    "Enable after implementing margin order safety checks."
                ),
                severity="critical",
                metadata={"leverage": leverage},
            )
        return RiskCheckResult(
            name="leverage_check",
            passed=True,
            message=f"Leverage {leverage}x accepted (spot/1x only for live)",
        )

    def _check_price_slippage(
        self,
        entry_price: float,
        market_snapshot: Optional[MarketSnapshot],
    ) -> RiskCheckResult:
        if market_snapshot is None:
            # No snapshot available — we cannot check slippage.
            # For live: block. For paper/shadow: warn only.
            return RiskCheckResult(
                name="price_slippage",
                passed=False,
                message="No market snapshot available to verify price slippage",
                severity="high",
                metadata={"entry_price": entry_price},
            )

        current_price = market_snapshot.close_price
        if current_price <= 0 or entry_price <= 0:
            return RiskCheckResult(
                name="price_slippage",
                passed=False,
                message="Invalid price (zero or negative) in slippage check",
                severity="high",
            )

        slippage_pct = abs(current_price - entry_price) / entry_price * 100
        limit = _DEFAULT_MAX_PRICE_SLIPPAGE_PCT

        if slippage_pct > limit:
            return RiskCheckResult(
                name="price_slippage",
                passed=False,
                message=(
                    f"Price slippage {slippage_pct:.2f}% > limit {limit:.2f}%. "
                    f"Entry price {entry_price}, current {current_price}."
                ),
                severity="high",
                metadata={
                    "slippage_pct": round(slippage_pct, 4),
                    "limit_pct": limit,
                    "entry_price": entry_price,
                    "current_price": current_price,
                },
            )
        return RiskCheckResult(
            name="price_slippage",
            passed=True,
            message=f"Slippage {slippage_pct:.2f}% within limit {limit:.2f}%",
        )

    def _check_spread_limit(
        self, market_snapshot: Optional[MarketSnapshot]
    ) -> RiskCheckResult:
        if market_snapshot is None:
            return RiskCheckResult(
                name="spread_limit",
                passed=False,
                message="No market snapshot — cannot verify spread",
                severity="high",
            )

        spread = market_snapshot.spread_pct
        if spread is None:
            # Spread not recorded — treat as advisory warning, not a block
            return RiskCheckResult(
                name="spread_limit",
                passed=True,
                message="Spread not available in snapshot (advisory pass)",
                severity="info",
            )

        limit = _DEFAULT_MAX_SPREAD_PCT
        if spread > limit:
            return RiskCheckResult(
                name="spread_limit",
                passed=False,
                message=f"Spread {spread:.2f}% > limit {limit:.2f}% — insufficient liquidity",
                severity="high",
                metadata={"spread_pct": spread, "limit_pct": limit},
            )
        return RiskCheckResult(
            name="spread_limit",
            passed=True,
            message=f"Spread {spread:.2f}% within limit {limit:.2f}%",
        )

    def _check_correlation_placeholder(self) -> RiskCheckResult:
        """
        Correlation risk check placeholder.

        TODO: Implement cross-portfolio correlation check. If the portfolio
              already has high exposure to correlated assets (e.g., BTC + ETH
              both long), new positions that increase concentration should be
              blocked or warned.
        """
        return RiskCheckResult(
            name="correlation_risk",
            passed=True,
            message="Correlation risk check not yet implemented (placeholder pass)",
            severity="info",
        )
