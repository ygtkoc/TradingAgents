"""
Tests for IdempotencyChecker.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.execution.idempotency import IdempotencyChecker
from tests.conftest import make_trade


@pytest.mark.asyncio
async def test_no_existing_trade_returns_none():
    checker = IdempotencyChecker()
    with patch.object(checker._repo, "find_by_decision_id", AsyncMock(return_value=None)):
        result = await checker.find_existing_trade("decision-001")
    assert result is None


@pytest.mark.asyncio
async def test_existing_trade_returned():
    existing = make_trade(trade_decision_id="decision-001")
    checker = IdempotencyChecker()
    with patch.object(checker._repo, "find_by_decision_id", AsyncMock(return_value=existing)):
        result = await checker.find_existing_trade("decision-001")
    assert result is not None
    assert result.id == "trade-001"


@pytest.mark.asyncio
async def test_find_called_with_correct_id():
    checker = IdempotencyChecker()
    mock_find = AsyncMock(return_value=None)
    with patch.object(checker._repo, "find_by_decision_id", mock_find):
        await checker.find_existing_trade("test-decision-123")
    mock_find.assert_called_once_with("test-decision-123")


@pytest.mark.asyncio
async def test_different_decision_ids_are_independent():
    trade_a = make_trade(trade_decision_id="decision-A")
    checker = IdempotencyChecker()

    async def _find(decision_id: str):
        return trade_a if decision_id == "decision-A" else None

    with patch.object(checker._repo, "find_by_decision_id", side_effect=_find):
        result_a = await checker.find_existing_trade("decision-A")
        result_b = await checker.find_existing_trade("decision-B")

    assert result_a is not None
    assert result_b is None
