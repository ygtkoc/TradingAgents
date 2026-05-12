"""
LifecycleRiskGuard — pre-action risk checks for position lifecycle.

Checks performed before any close action:
  1. Slippage: compare expected close price vs current market price
  2. Spread: block close if spread is extreme
  3. Max drawdown check (placeholder)
  4. Quantity sanity (close qty <= trade quantity)

These checks are advisory for paper/shadow. For live, they block the action.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from src.config import settings
from src.db.models import MarketSnapshot, PlatformSettings, Trade
from src.logging_config import get_logger

log = get_logger(__name__)


@dataclass
class RiskCheckResult:
    name:     str
    passed:   bool
    message:  str
    severity: str = "medium"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LifecycleRiskGuardResult:
    blocked: bool
    reason:  str
    checks:  list[RiskCheckResult] = field(default_factory=list)

    @property
    def failed_checks(self) -> list[RiskCheckResult]:
        return [c for c in self.checks if not c.passed]

    def to_dict(self) -> dict:
        return {
            "blocked": self.blocked,
            "reason":  self.reason,
            "checks":  [
                {"name": c.name, "passed": c.passed,
                 "message": c.message, "severity": c.severity}
                for c in self.checks
            ],
        }


class LifecycleRiskGuard:
    """
    Validates risk conditions before a lifecycle close action.
    """

    def check_before_close(
        self,
        *,
        trade: Trade,
        expected_close_price: float,
        market_snapshot: Optional[MarketSnapshot],
        platform_settings: PlatformSettings,
        close_quantity: Optional[float] = None,
    ) -> LifecycleRiskGuardResult:
        checks: list[RiskCheckResult] = []
        is_live = trade.is_live

        # ── 1. Close price slippage ───────────────────────────────────────────
        checks.append(self._check_slippage(
            expected_close_price=expected_close_price,
            market_snapshot=market_snapshot,
            max_slippage_pct=platform_settings.max_allowed_slippage_pct,
            is_live=is_live,
        ))

        # ── 2. Spread limit ───────────────────────────────────────────────────
        checks.append(self._check_spread(market_snapshot, is_live))

        # ── 3. Quantity sanity ────────────────────────────────────────────────
        qty = close_quantity or trade.effective_quantity
        checks.append(self._check_quantity(qty, trade))

        # ── 4. Drawdown placeholder ───────────────────────────────────────────
        checks.append(self._check_drawdown_placeholder())

        # For live: block on high/critical severity failures
        # For paper/shadow: all checks are advisory
        if is_live:
            failed  = [c for c in checks if not c.passed and c.severity in ("high", "critical")]
            blocked = bool(failed)
        else:
            failed  = []
            blocked = False

        return LifecycleRiskGuardResult(
            blocked=blocked,
            reason="; ".join(c.message for c in failed) if failed else "all checks passed",
            checks=checks,
        )

    # ── Individual checks ──────────────────────────────────────────────────────

    def _check_slippage(
        self,
        expected_close_price: float,
        market_snapshot: Optional[MarketSnapshot],
        max_slippage_pct: float,
        is_live: bool,
    ) -> RiskCheckResult:
        if market_snapshot is None:
            sev = "high" if is_live else "info"
            return RiskCheckResult(
                name="close_slippage",
                passed=not is_live,  # block live if no snapshot
                message="No market snapshot — cannot verify close price slippage",
                severity=sev,
            )

        current = market_snapshot.close_price
        if current <= 0 or expected_close_price <= 0:
            return RiskCheckResult(
                name="close_slippage",
                passed=False,
                message="Invalid price (zero/negative) in slippage check",
                severity="high",
            )

        slippage_pct = abs(current - expected_close_price) / expected_close_price * 100
        if slippage_pct > max_slippage_pct:
            return RiskCheckResult(
                name="close_slippage",
                passed=False,
                message=(
                    f"Close price slippage {slippage_pct:.2f}% > limit {max_slippage_pct:.2f}%"
                ),
                severity="high",
                metadata={
                    "slippage_pct":    round(slippage_pct, 4),
                    "expected_price":  expected_close_price,
                    "current_price":   current,
                    "max_slippage_pct": max_slippage_pct,
                },
            )
        return RiskCheckResult(
            name="close_slippage",
            passed=True,
            message=f"Slippage {slippage_pct:.2f}% within limit {max_slippage_pct:.2f}%",
        )

    def _check_spread(
        self, market_snapshot: Optional[MarketSnapshot], is_live: bool
    ) -> RiskCheckResult:
        if market_snapshot is None or market_snapshot.spread_pct is None:
            return RiskCheckResult(
                name="spread_limit",
                passed=True,
                message="Spread not available (advisory pass)",
                severity="info",
            )
        limit = settings.max_spread_pct if hasattr(settings, "max_spread_pct") else 2.0
        if market_snapshot.spread_pct > limit:
            return RiskCheckResult(
                name="spread_limit",
                passed=False,
                message=f"Spread {market_snapshot.spread_pct:.2f}% > limit {limit:.2f}%",
                severity="high",
                metadata={"spread": market_snapshot.spread_pct, "limit": limit},
            )
        return RiskCheckResult(
            name="spread_limit",
            passed=True,
            message=f"Spread {market_snapshot.spread_pct:.2f}% within limit",
        )

    def _check_quantity(self, close_quantity: float, trade: Trade) -> RiskCheckResult:
        if close_quantity <= 0:
            return RiskCheckResult(
                name="close_quantity",
                passed=False,
                message=f"Invalid close quantity: {close_quantity}",
                severity="critical",
            )
        max_qty = trade.effective_quantity
        if close_quantity > max_qty * 1.001:  # 0.1% tolerance for float rounding
            return RiskCheckResult(
                name="close_quantity",
                passed=False,
                message=(
                    f"Close quantity {close_quantity} > trade quantity {max_qty}"
                ),
                severity="critical",
                metadata={"close_qty": close_quantity, "trade_qty": max_qty},
            )
        return RiskCheckResult(
            name="close_quantity",
            passed=True,
            message=f"Close quantity {close_quantity} valid",
        )

    def _check_drawdown_placeholder(self) -> RiskCheckResult:
        """
        Placeholder for max drawdown check.
        TODO: Compare trade's unrealized_pnl against bot.max_daily_loss_pct.
        """
        return RiskCheckResult(
            name="max_drawdown",
            passed=True,
            message="Drawdown check not yet implemented (placeholder pass)",
            severity="info",
        )
