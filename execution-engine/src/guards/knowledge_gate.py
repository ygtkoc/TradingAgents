from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from src.db.models import MarketSnapshot, TradeDecision


@dataclass
class KnowledgeGateResult:
    blocked: bool
    score: int
    verdict: str
    supporting_rules: list[dict[str, Any]] = field(default_factory=list)
    violated_rules: list[dict[str, Any]] = field(default_factory=list)
    retrieved_chunks: list[dict[str, Any]] = field(default_factory=list)
    critic_summary: str = ""
    visual_annotations: dict[str, Any] = field(default_factory=dict)


class KnowledgeGate:
    """Heuristic v1 of Lucrandos Trading Brain.

    This is intentionally deterministic: imported knowledge/rules can explain
    and veto a trade without relying on a remote LLM in the execution hot path.
    """

    BLOCK_THRESHOLD = 55
    REVIEW_THRESHOLD = 75

    def evaluate(
        self,
        *,
        decision: TradeDecision,
        market_snapshot: Optional[MarketSnapshot],
        rules: list[dict],
        chunks: list[dict],
        duplicate_exposure_blocked: bool = False,
    ) -> KnowledgeGateResult:
        score = 100
        supporting: list[dict[str, Any]] = []
        violated: list[dict[str, Any]] = []

        context = self._context(decision, market_snapshot)
        for rule in rules:
            code = str(rule.get("rule_code") or "")
            weight = int(rule.get("weight") or 10)
            passed, reason = self._check_rule(code, context, duplicate_exposure_blocked)
            item = {
                "rule_code": code,
                "title": rule.get("title"),
                "category": rule.get("category"),
                "severity": rule.get("severity"),
                "reason": reason,
                "weight": weight,
            }
            if passed:
                supporting.append(item)
            else:
                violated.append(item)
                score -= weight

        score = max(0, min(100, score))
        verdict = "pass" if score >= self.REVIEW_THRESHOLD else "review"
        critical_violations = [v for v in violated if v.get("severity") == "critical"]
        if score < self.BLOCK_THRESHOLD or critical_violations:
            verdict = "block"

        visual = self._visual_annotations(decision, market_snapshot, context)
        summary = self._critic_summary(
            decision=decision,
            score=score,
            verdict=verdict,
            violated=violated,
            supporting=supporting,
            chunks=chunks,
        )

        return KnowledgeGateResult(
            blocked=verdict == "block",
            score=score,
            verdict=verdict,
            supporting_rules=supporting[:10],
            violated_rules=violated[:10],
            retrieved_chunks=[
                {
                    "id": c.get("id"),
                    "source_id": c.get("source_id"),
                    "tags": c.get("tags") or [],
                    "excerpt": str(c.get("content") or "")[:420],
                }
                for c in chunks[:8]
            ],
            critic_summary=summary,
            visual_annotations=visual,
        )

    def tags_for_decision(self, decision: TradeDecision) -> list[str]:
        tags = {"risk", "stop-loss", "take-profit", "position-sizing"}
        final = str(decision.final_decision or "")
        direction = str(decision.direction or "")
        if "long" in final or direction == "long":
            tags.add("long")
        if "short" in final or direction == "short":
            tags.add("short")
        for key in ("breakout", "trend", "support", "resistance", "liquidity"):
            if key in str(decision.score_summary).lower() or key in str(decision.risk_summary).lower():
                tags.add(key)
        return sorted(tags)

    def _context(self, decision: TradeDecision, market_snapshot: Optional[MarketSnapshot]) -> dict[str, Any]:
        risk = decision.risk_summary or {}
        entry = self._num(risk.get("entry_price")) or self._num(risk.get("entry")) or self._num(market_snapshot.close_price if market_snapshot else None)
        stop = self._num(risk.get("stop_loss")) or self._num(risk.get("stop"))
        take_profit = self._num(risk.get("take_profit"))
        rr = self._num(risk.get("risk_reward_ratio")) or self._num(risk.get("rr"))

        if rr is None and entry and stop and take_profit:
            risk_distance = abs(entry - stop)
            if risk_distance > 0:
                rr = abs(take_profit - entry) / risk_distance

        direction = "short" if decision.final_decision == "open_short" or decision.direction == "short" else "long"
        move_from_open = None
        if market_snapshot and market_snapshot.open_price:
            move_from_open = ((market_snapshot.close_price - market_snapshot.open_price) / market_snapshot.open_price) * 100.0

        return {
            "entry": entry,
            "stop": stop,
            "take_profit": take_profit,
            "rr": rr,
            "direction": direction,
            "move_from_open": move_from_open,
            "market": market_snapshot,
        }

    def _check_rule(self, code: str, context: dict[str, Any], duplicate_exposure_blocked: bool) -> tuple[bool, str]:
        if code == "stop_required":
            return bool(context["stop"]), "Stop/invalidation is present." if context["stop"] else "Missing stop/invalidation."
        if code == "minimum_rr":
            rr = context["rr"]
            return bool(rr and rr >= 1.5), f"Planned RR is {rr:.2f}." if rr else "Reward/risk could not be proven."
        if code == "no_duplicate_exposure":
            return not duplicate_exposure_blocked, "No duplicate exposure detected." if not duplicate_exposure_blocked else "Duplicate exposure exists."
        if code == "avoid_fomo_chase":
            move = abs(float(context["move_from_open"] or 0))
            return move < 6.0, f"Current candle move is {move:.2f}%."
        if code == "visual_explanation_required":
            return bool(context["entry"] and context["stop"]), "Visual annotations can be generated." if context["entry"] and context["stop"] else "Visual annotations lack entry/stop."
        return True, "Custom knowledge rule recorded for review."

    def _visual_annotations(
        self,
        decision: TradeDecision,
        market_snapshot: Optional[MarketSnapshot],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        entry = context["entry"]
        stop = context["stop"]
        take_profit = context["take_profit"]
        direction = context["direction"]
        high = self._num(market_snapshot.high_price if market_snapshot else None)
        low = self._num(market_snapshot.low_price if market_snapshot else None)
        close = self._num(market_snapshot.close_price if market_snapshot else None) or entry

        lines = []
        if entry:
            lines.append({"type": "entry", "price": entry, "label": f"{direction.upper()} entry", "reason": "Execution entry proposed by risk summary."})
        if stop:
            lines.append({"type": "invalidation", "price": stop, "label": "Invalidation / stop", "reason": "Trade thesis is invalidated at this level."})
        if take_profit:
            lines.append({"type": "take_profit", "price": take_profit, "label": "Primary take profit", "reason": "Reward target derived from planned R multiple."})
        if low:
            lines.append({"type": "support", "price": low, "label": "Observed support", "reason": "Latest market snapshot low."})
        if high:
            lines.append({"type": "resistance", "price": high, "label": "Observed resistance", "reason": "Latest market snapshot high."})

        trend = []
        if market_snapshot:
            trend = [
                {"x": "open", "price": market_snapshot.open_price},
                {"x": "close", "price": market_snapshot.close_price},
            ]

        return {
            "symbol": decision.symbol,
            "direction": direction,
            "last_price": close,
            "lines": lines,
            "trendline": {
                "points": trend,
                "reason": "Trendline connects the latest snapshot open and close until richer candle structure is attached.",
            },
        }

    def _critic_summary(
        self,
        *,
        decision: TradeDecision,
        score: int,
        verdict: str,
        violated: list[dict[str, Any]],
        supporting: list[dict[str, Any]],
        chunks: list[dict],
    ) -> str:
        if verdict == "block":
            lead = "Knowledge gate blocked this decision before execution."
        elif verdict == "review":
            lead = "Knowledge gate requires operator review before this setup should be trusted."
        else:
            lead = "Knowledge gate found the setup consistent with the current rule base."
        problems = "; ".join(str(v.get("reason")) for v in violated[:3]) or "No major violations."
        evidence = len(chunks)
        return f"{lead} Score {score}/100. Main critique: {problems} Retrieved knowledge snippets: {evidence}."

    def _num(self, value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            next_value = float(value)
            return next_value if next_value > 0 else None
        except (TypeError, ValueError):
            return None
