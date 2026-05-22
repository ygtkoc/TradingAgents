import pytest

from src.agents.risk import RewardPlanAgent
from src.db.models import AgentCategory, AgentDefinition, TradeDirection
from tests.conftest import make_signal


@pytest.mark.asyncio
async def test_reward_plan_agent_writes_scaled_plan_to_state():
    definition = AgentDefinition(
        id="agent-reward-plan",
        name="reward_plan_agent",
        display_name="Reward Plan Agent",
        agent_type="RewardPlanAgent",
        category=AgentCategory.RISK,
        enabled=True,
        can_veto=True,
    )
    agent = RewardPlanAgent(definition)
    state = {
        "signal": make_signal(direction=TradeDirection.LONG.value),
        "market_snapshot": {"close_price": 100.0},
        "price_history": [],
        "bot": {
            "metadata": {"stop_loss_pct": 2.0, "max_reward_r": 5.0},
            "strategy_type": "momentum",
        },
        "user_settings": {"max_reward_r": 3.0, "min_reward_r": 1.5},
        "risk_score": 75.0,
        "atr_pct": 1.0,
    }

    result = await agent.run(state)

    assert result.veto is False
    assert state["reward_plan"]["selected_reward_r"] <= 3.0
    assert state["reward_plan"]["selected_reward_r"] < 3.0
    assert len(state["reward_plan"]["levels"]) == 3
    assert result.output["take_profit"] == state["reward_plan"]["levels"][-1]["price"]


@pytest.mark.asyncio
async def test_reward_plan_agent_treats_max_r_as_ceiling_not_target():
    definition = AgentDefinition(
        id="agent-reward-plan",
        name="reward_plan_agent",
        display_name="Reward Plan Agent",
        agent_type="RewardPlanAgent",
        category=AgentCategory.RISK,
        enabled=True,
        can_veto=True,
    )
    agent = RewardPlanAgent(definition)

    async def run_with_max(max_r: float) -> float:
        state = {
            "signal": make_signal(direction=TradeDirection.LONG.value),
            "market_snapshot": {"close_price": 100.0},
            "price_history": [],
            "bot": {
                "metadata": {"stop_loss_pct": 2.0},
                "strategy_type": "momentum",
            },
            "user_settings": {"max_reward_r": max_r, "min_reward_r": 1.5},
            "risk_score": 75.0,
            "atr_pct": 1.0,
        }
        result = await agent.run(state)
        assert result.veto is False
        selected = float(state["reward_plan"]["selected_reward_r"])
        assert selected < max_r
        return selected

    selected_3r = await run_with_max(3.0)
    selected_5r = await run_with_max(5.0)

    assert selected_3r == pytest.approx(2.5)
    assert selected_3r < selected_5r < 5.0
