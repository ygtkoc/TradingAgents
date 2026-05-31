from src.guards.knowledge_gate import KnowledgeGate
from tests.conftest import make_decision, make_market_snapshot


def test_knowledge_gate_matches_pattern_and_exports_overlay():
    gate = KnowledgeGate()
    decision = make_decision(
        score_summary={
            "setup": "Bull flag breakout after a strong impulse. Retest held with volume."
        },
        risk_summary={
            "entry_price": 100.0,
            "stop_loss": 96.0,
            "take_profit": 108.0,
            "risk_reward_ratio": 2.0,
        },
    )
    chunks = [
        {
            "id": "chunk-1",
            "source_id": "source-1",
            "content": "Bull Flag Continuation requires breakout confirmation.",
            "tags": ["bull_flag", "continuation", "breakout", "trend"],
            "metadata": {
                "source_title": "Bull Flag Continuation",
                "source_metadata": {
                    "category": "chart_pattern",
                    "priority": "high",
                    "confirmation_logic": "A candle closes above flag resistance with volume expansion.",
                    "invalidation_logic": "Price closes below the flag low.",
                    "common_mistake": "Entering inside the flag before breakout confirmation.",
                },
            },
        }
    ]

    result = gate.evaluate(
        decision=decision,
        market_snapshot=make_market_snapshot(close_price=101.0),
        rules=[],
        chunks=chunks,
    )

    assert result.verdict == "pass"
    assert result.retrieved_chunks[0]["id"] == "chunk-1"
    assert result.visual_annotations["knowledge_overlays"][0]["title"] == "Bull Flag Continuation"
    assert "Bull Flag Continuation" in result.critic_summary
    assert any(item["rule_code"] == "knowledge_pattern_match" for item in result.supporting_rules)


def test_knowledge_gate_penalizes_missing_confirmation_language():
    gate = KnowledgeGate()
    decision = make_decision(
        score_summary={"setup": "Possible bull flag."},
        risk_summary={
            "entry_price": 100.0,
            "stop_loss": 96.0,
            "take_profit": 108.0,
            "risk_reward_ratio": 2.0,
        },
    )
    chunks = [
        {
            "id": "chunk-1",
            "source_id": "source-1",
            "content": "Bull Flag Continuation requires breakout confirmation.",
            "tags": ["bull_flag", "continuation", "breakout"],
            "metadata": {
                "source_title": "Bull Flag Continuation",
                "source_metadata": {
                    "category": "chart_pattern",
                    "priority": "high",
                    "confirmation_logic": "A candle closes above flag resistance with volume expansion.",
                    "invalidation_logic": "Price closes below the flag low.",
                },
            },
        }
    ]

    result = gate.evaluate(
        decision=decision,
        market_snapshot=make_market_snapshot(close_price=101.0),
        rules=[],
        chunks=chunks,
    )

    assert result.score == 94
    assert any(item["rule_code"] == "confirmation_logic_missing" for item in result.violated_rules)
