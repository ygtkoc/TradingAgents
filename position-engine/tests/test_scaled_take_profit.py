import pytest

from src.lifecycle.action import ActionType
from src.lifecycle.scaled_take_profit import (
    check_scaled_take_profit,
    next_stop_after_tp,
    next_take_profit_after_tp,
)
from tests.conftest import make_trade


def _plan():
    return {
        "mode": "scaled_take_profit",
        "selected_reward_r": 3.0,
        "levels": [
            {"level": 1, "label": "TP1", "price": 101.0, "r": 1.0, "close_pct": 0.00, "status": "pending"},
            {"level": 2, "label": "TP2", "price": 102.0, "r": 2.0, "close_pct": 0.50, "status": "pending"},
            {"level": 3, "label": "TP3", "price": 103.0, "r": 3.0, "close_pct": 0.50, "status": "pending"},
        ],
    }


def test_tp1_moves_stop_to_breakeven_without_closing_for_long():
    trade = make_trade(entry_price=100.0, stop_loss=98.0, quantity=10.0, filled_quantity=10.0, metadata={"reward_plan": _plan()})
    action = check_scaled_take_profit(trade, current_price=101.1)
    assert action.action_type == ActionType.UPDATE_STOP_LOSS
    assert action.metadata["tp_level"] == 1
    assert action.metadata["close_quantity"] == pytest.approx(0.0)
    assert action.new_stop_loss == pytest.approx(100.0)
    assert action.metadata["is_final_tp"] is False


def test_waits_for_next_pending_level():
    plan = _plan()
    plan["levels"][0]["status"] = "hit"
    trade = make_trade(entry_price=100.0, quantity=10.0, filled_quantity=10.0, metadata={"reward_plan": plan})
    action = check_scaled_take_profit(trade, current_price=102.1)
    assert action.metadata["tp_level"] == 2
    assert action.metadata["close_quantity"] == pytest.approx(5.0)


def test_final_level_closes_remaining_quantity():
    plan = _plan()
    plan["levels"][0]["status"] = "hit"
    plan["levels"][1]["status"] = "hit"
    trade = make_trade(entry_price=100.0, quantity=10.0, filled_quantity=4.2, metadata={"reward_plan": plan})
    action = check_scaled_take_profit(trade, current_price=103.1)
    assert action.metadata["tp_level"] == 3
    assert action.metadata["close_quantity"] == pytest.approx(4.2)
    assert action.metadata["is_final_tp"] is True


def test_multi_level_candle_range_closes_through_highest_hit_level():
    trade = make_trade(entry_price=100.0, quantity=10.0, filled_quantity=10.0, metadata={"reward_plan": _plan()})
    action = check_scaled_take_profit(trade, current_price=101.2, high_price=102.2)

    assert action.action_type == ActionType.CLOSE_TAKE_PROFIT
    assert action.metadata["tp_level"] == 2
    assert action.metadata["tp_levels_hit"] == [1, 2]
    assert action.metadata["close_quantity"] == pytest.approx(5.0)
    assert action.metadata["is_final_tp"] is False


def test_multi_level_candle_range_closes_final_level():
    trade = make_trade(entry_price=100.0, quantity=10.0, filled_quantity=10.0, metadata={"reward_plan": _plan()})
    action = check_scaled_take_profit(trade, current_price=101.2, high_price=103.2)

    assert action.action_type == ActionType.CLOSE_TAKE_PROFIT
    assert action.metadata["tp_level"] == 3
    assert action.metadata["tp_levels_hit"] == [1, 2, 3]
    assert action.metadata["close_quantity"] == pytest.approx(10.0)
    assert action.metadata["is_final_tp"] is True


def test_next_stop_moves_to_breakeven_after_tp1():
    trade = make_trade(entry_price=100.0, stop_loss=98.0)
    assert next_stop_after_tp(trade, _plan(), 1) == pytest.approx(100.0)


def test_next_take_profit_moves_to_next_pending_level():
    plan = _plan()
    plan["levels"][0]["status"] = "hit"
    assert next_take_profit_after_tp(plan, 1) == pytest.approx(102.0)


def test_short_tp1_triggers_when_price_falls():
    plan = _plan()
    for level in plan["levels"]:
        level["price"] = 100.0 - level["level"]
    trade = make_trade(
        direction="short",
        side="sell",
        entry_price=100.0,
        quantity=10.0,
        filled_quantity=10.0,
        metadata={"reward_plan": plan},
    )
    action = check_scaled_take_profit(trade, current_price=98.9)
    assert action.action_type == ActionType.UPDATE_STOP_LOSS
    assert action.metadata["tp_level"] == 1


def test_missing_plan_falls_back_to_risk_reward_ratio():
    trade = make_trade(
        entry_price=100.0,
        stop_loss=98.0,
        take_profit=106.0,
        risk_reward_ratio=3.0,
        quantity=10.0,
        filled_quantity=10.0,
    )

    action = check_scaled_take_profit(trade, current_price=102.1)

    assert action.action_type == ActionType.UPDATE_STOP_LOSS
    assert action.metadata["tp_level"] == 1
    assert action.metadata["tp_price"] == pytest.approx(102.0)
    assert action.metadata["close_quantity"] == pytest.approx(0.0)
    assert action.metadata["reward_plan"]["source"] == "position_engine_fallback"


def test_missing_plan_can_derive_r_from_final_take_profit():
    trade = make_trade(
        entry_price=100.0,
        stop_loss=98.0,
        take_profit=106.0,
        quantity=10.0,
        filled_quantity=10.0,
    )

    action = check_scaled_take_profit(trade, current_price=102.1)

    assert action.action_type == ActionType.UPDATE_STOP_LOSS
    assert action.metadata["tp_r"] == pytest.approx(1.0)
