from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXECUTION_ENGINE_ROOT = ROOT / "execution-engine"
if str(EXECUTION_ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(EXECUTION_ENGINE_ROOT))

from src.db.repositories import TradeDecisionRepository
from src.execution.engine import ExecutionEngine


async def main() -> None:
    repo = TradeDecisionRepository()
    candidate_ids = await repo.fetch_executable_ids(limit=10)
    print({"candidate_ids": candidate_ids})

    claimed = None
    for decision_id in candidate_ids:
        decision = await repo.get_by_id(decision_id)
        if decision is None or decision.mode != "paper":
            continue
        claimed = await repo.claim_for_execution(decision_id, "debug-execution-once")
        if claimed is not None:
            break

    if claimed is None:
        raise RuntimeError("No claimable paper decision found")

    print(
        {
            "claimed_decision_id": claimed.id,
            "mode": claimed.mode,
            "symbol": claimed.symbol,
        }
    )

    engine = ExecutionEngine()
    try:
        await engine.run(claimed)
    except Exception as exc:
        print({"stage": "execution.run", "exception": repr(exc)})
        raise

    refreshed = await repo.get_by_id(claimed.id)
    print(
        {
            "decision_id": refreshed.id if refreshed else claimed.id,
            "execution_status": refreshed.execution_status if refreshed else None,
            "linked_trade_id": refreshed.linked_trade_id if refreshed else None,
            "execution_error": refreshed.execution_error if refreshed else None,
        }
    )


if __name__ == "__main__":
    asyncio.run(main())
