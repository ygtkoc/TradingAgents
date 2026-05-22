import pytest

from src.execution.reward_plan import build_reward_plan, final_take_profit, normalize_reward_plan


def test_build_reward_plan_creates_three_ordered_long_targets():
    plan = build_reward_plan(
        entry_price=100.0,
        stop_loss=98.0,
        direction="long",
        requested_reward_r=3.0,
        max_reward_r=5.0,
    )
    assert plan["selected_reward_r"] == pytest.approx(3.0)
    assert [level["label"] for level in plan["levels"]] == ["TP1", "TP2", "TP3"]
    assert [level["price"] for level in plan["levels"]] == pytest.approx([102.0, 103.9, 106.0])
    assert sum(level["close_pct"] for level in plan["levels"]) == pytest.approx(1.0)


def test_build_reward_plan_caps_to_user_max_r():
    plan = build_reward_plan(
        entry_price=100.0,
        stop_loss=98.0,
        direction="long",
        requested_reward_r=8.0,
        max_reward_r=5.0,
    )
    assert plan["selected_reward_r"] == pytest.approx(5.0)


def test_build_reward_plan_without_requested_r_uses_conservative_default():
    plan = build_reward_plan(
        entry_price=100.0,
        stop_loss=98.0,
        direction="long",
        requested_reward_r=None,
        max_reward_r=5.0,
        min_reward_r=1.5,
    )

    assert plan["selected_reward_r"] == pytest.approx(2.0)
    assert final_take_profit(plan) == pytest.approx(104.0)


def test_normalize_reward_plan_uses_agent_selected_r():
    risk = {"reward_plan": {"selected_reward_r": 2.5, "close_profile": "runner"}}
    plan = normalize_reward_plan(
        risk_summary=risk,
        entry_price=100.0,
        stop_loss=102.0,
        direction="short",
        max_reward_r=5.0,
        min_reward_r=1.5,
    )
    assert plan["selected_reward_r"] == pytest.approx(2.5)
    assert final_take_profit(plan) == pytest.approx(95.0)
