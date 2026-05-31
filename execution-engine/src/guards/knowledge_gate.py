from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
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
        knowledge_evidence = self._rank_chunks(chunks, context)
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

        evidence_result = self._evaluate_evidence(context, knowledge_evidence)
        supporting.extend(evidence_result["supporting"])
        violated.extend(evidence_result["violated"])
        score -= int(evidence_result["penalty"])

        score = max(0, min(100, score))
        verdict = "pass" if score >= self.REVIEW_THRESHOLD else "review"
        critical_violations = [v for v in violated if v.get("severity") == "critical"]
        if score < self.BLOCK_THRESHOLD or critical_violations:
            verdict = "block"

        visual = self._visual_annotations(decision, market_snapshot, context, knowledge_evidence)
        summary = self._critic_summary(
            decision=decision,
            score=score,
            verdict=verdict,
            violated=violated,
            supporting=supporting,
            chunks=knowledge_evidence,
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
                for c in knowledge_evidence[:8]
            ],
            critic_summary=summary,
            visual_annotations=visual,
        )

    def tags_for_decision(self, decision: TradeDecision) -> list[str]:
        tags = {"risk", "stop-loss", "take-profit", "position-sizing"}
        final = str(decision.final_decision or "").lower()
        direction = str(decision.direction or "").lower()
        text = self._decision_text(decision).lower()
        if "long" in final or direction == "long":
            tags.update({"long", "bullish"})
        if "short" in final or direction == "short":
            tags.update({"short", "bearish"})
        keyword_tags = {
            "breakout": ("breakout", "break above", "broke above"),
            "breakdown": ("breakdown", "break below", "broke below"),
            "trend": ("trend", "continuation", "impulse"),
            "support": ("support", "demand"),
            "resistance": ("resistance", "supply"),
            "liquidity": ("liquidity", "sweep", "stop hunt"),
            "reversal": ("reversal", "reject", "reclaim"),
            "compression": ("compression", "contract", "squeeze"),
            "bull_flag": ("bull flag", "bull_flag"),
            "bear_flag": ("bear flag", "bear_flag"),
            "ascending_triangle": ("ascending triangle", "ascending_triangle"),
            "descending_triangle": ("descending triangle", "descending_triangle"),
            "head_and_shoulders": ("head and shoulders", "head_shoulders"),
            "double_top": ("double top", "double_top"),
            "double_bottom": ("double bottom", "double_bottom"),
            "wedge": ("wedge", "rising wedge", "falling wedge"),
            "range": ("range", "shelf", "base"),
        }
        for tag, terms in keyword_tags.items():
            if any(term in text for term in terms):
                tags.add(tag)
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
            "text": self._decision_text(decision).lower(),
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

    def _evaluate_evidence(self, context: dict[str, Any], chunks: list[dict]) -> dict[str, Any]:
        supporting: list[dict[str, Any]] = []
        violated: list[dict[str, Any]] = []
        penalty = 0

        if not chunks:
            return {
                "supporting": supporting,
                "violated": [{
                    "rule_code": "knowledge_retrieval_missing",
                    "title": "No relevant knowledge retrieved",
                    "category": "knowledge",
                    "severity": "medium",
                    "reason": "Trading Brain could not match this decision to imported knowledge.",
                    "weight": 8,
                }],
                "penalty": 8,
            }

        top = chunks[0]
        meta = self._metadata(top)
        supporting.append({
            "rule_code": "knowledge_pattern_match",
            "title": top.get("metadata", {}).get("source_title") or "Knowledge evidence matched",
            "category": meta.get("category") or "knowledge",
            "severity": "medium",
            "reason": self._evidence_reason(top),
            "weight": 0,
        })

        if meta.get("confirmation_logic") and not self._mentions_confirmation(context["text"]):
            penalty += 6
            violated.append({
                "rule_code": "confirmation_logic_missing",
                "title": "Pattern confirmation not explicit",
                "category": meta.get("category") or "knowledge",
                "severity": "medium",
                "reason": f"Matched knowledge expects confirmation: {meta.get('confirmation_logic')}",
                "weight": 6,
            })
        if meta.get("invalidation_logic") and not context.get("stop"):
            penalty += 14
            violated.append({
                "rule_code": "knowledge_invalidation_missing",
                "title": "Pattern invalidation missing",
                "category": meta.get("category") or "risk",
                "severity": "high",
                "reason": f"Matched knowledge requires invalidation: {meta.get('invalidation_logic')}",
                "weight": 14,
            })

        return {"supporting": supporting, "violated": violated, "penalty": penalty}

    def _visual_annotations(
        self,
        decision: TradeDecision,
        market_snapshot: Optional[MarketSnapshot],
        context: dict[str, Any],
        chunks: list[dict],
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
            "knowledge_overlays": [self._overlay_from_chunk(chunk) for chunk in chunks[:5]],
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
        pattern = ""
        if chunks:
            meta = self._metadata(chunks[0])
            source_title = chunks[0].get("metadata", {}).get("source_title") or chunks[0].get("source_id")
            pattern = (
                f" Best match: {source_title}. "
                f"Confirmation: {meta.get('confirmation_logic') or 'not specified'}. "
                f"Invalidation: {meta.get('invalidation_logic') or 'not specified'}."
            )
        return f"{lead} Score {score}/100. Main critique: {problems}.{pattern} Retrieved knowledge snippets: {evidence}."

    def _rank_chunks(self, chunks: list[dict], context: dict[str, Any]) -> list[dict]:
        text_tokens = self._tokens(context.get("text") or "")

        def score(chunk: dict) -> int:
            meta = self._metadata(chunk)
            chunk_text = f"{chunk.get('content') or ''} {json.dumps(meta, ensure_ascii=False)}".lower()
            tags = {str(tag).lower() for tag in chunk.get("tags") or []}
            points = len(tags.intersection(text_tokens)) * 8
            points += len(self._tokens(chunk_text).intersection(text_tokens))
            if context.get("direction") == "long" and {"bullish", "breakout", "long"}.intersection(tags):
                points += 6
            if context.get("direction") == "short" and {"bearish", "breakdown", "short"}.intersection(tags):
                points += 6
            priority = str(meta.get("priority") or "").lower()
            if priority == "critical":
                points += 4
            elif priority == "high":
                points += 2
            return points

        ranked = sorted(chunks, key=score, reverse=True)
        return [chunk for chunk in ranked if score(chunk) > 0] or ranked[:8]

    def _overlay_from_chunk(self, chunk: dict) -> dict[str, Any]:
        meta = self._metadata(chunk)
        return {
            "source_id": chunk.get("source_id"),
            "title": chunk.get("metadata", {}).get("source_title"),
            "tags": chunk.get("tags") or [],
            "category": meta.get("category"),
            "confirmation_logic": meta.get("confirmation_logic"),
            "invalidation_logic": meta.get("invalidation_logic"),
            "common_mistake": meta.get("common_mistake"),
        }

    def _metadata(self, chunk: dict) -> dict[str, Any]:
        metadata = chunk.get("metadata") or {}
        if not isinstance(metadata, dict):
            return {}
        source_metadata = metadata.get("source_metadata")
        if isinstance(source_metadata, dict):
            return {**metadata, **source_metadata}
        return metadata

    def _evidence_reason(self, chunk: dict) -> str:
        meta = self._metadata(chunk)
        reason = []
        if meta.get("confirmation_logic"):
            reason.append(f"confirmation: {meta['confirmation_logic']}")
        if meta.get("invalidation_logic"):
            reason.append(f"invalidation: {meta['invalidation_logic']}")
        if meta.get("common_mistake"):
            reason.append(f"common mistake: {meta['common_mistake']}")
        return "; ".join(reason) or "Imported knowledge matched the decision context."

    def _mentions_confirmation(self, text: str) -> bool:
        return any(
            term in text
            for term in (
                "confirm",
                "confirmation",
                "close above",
                "close below",
                "breakout",
                "breakdown",
                "retest",
                "volume",
                "hold",
                "reject",
                "reclaim",
            )
        )

    def _decision_text(self, decision: TradeDecision) -> str:
        payload = {
            "score_summary": decision.score_summary,
            "risk_summary": decision.risk_summary,
            "security_summary": decision.security_summary,
            "veto_summary": decision.veto_summary,
            "agent_outputs_snapshot": decision.agent_outputs_snapshot,
            "metadata": decision.metadata,
            "symbol": decision.symbol,
            "direction": decision.direction,
            "final_decision": decision.final_decision,
        }
        return json.dumps(payload, ensure_ascii=False, default=str)

    def _tokens(self, value: str) -> set[str]:
        return {
            token
            for token in re.split(r"[^a-zA-Z0-9_]+", value.lower())
            if len(token) >= 3
        }

    def _num(self, value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            next_value = float(value)
            return next_value if next_value > 0 else None
        except (TypeError, ValueError):
            return None
