from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT_ENGINE_ROOT = ROOT / "agent-engine"
if str(AGENT_ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ENGINE_ROOT))

from src.db.models import AgentRunInsert, AgentRunStatus, Signal  # noqa: E402
from src.db.repositories import AgentRunRepository, BotRepository  # noqa: E402
from src.db.supabase_client import get_client, log_startup_auth, run_startup_self_test  # noqa: E402
from src.orchestration.graph import TradingPipeline  # noqa: E402
from src.services.metadata import sanitize_metadata  # noqa: E402
from src.utils.time import utcnow_iso  # noqa: E402


async def _fetch_signal() -> Signal | None:
    client = get_client()

    def _select():
        return (
            client.table("signals")
            .select("*")
            .in_("status", ["pending", "processing"])
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

    result = await asyncio.to_thread(_select)
    if not result.data:
        return None
    return Signal.model_validate(result.data[0])


async def main() -> int:
    log_startup_auth()
    run_startup_self_test()

    signal_row = await _fetch_signal()
    if signal_row is None:
        print("debug.no_signal")
        return 1

    print(f"debug.signal id={signal_row.id} symbol={signal_row.symbol} status={signal_row.status.value}")

    bot_repo = BotRepository()
    bot = await bot_repo.get_bot(signal_row.bot_id)
    config = await bot_repo.get_active_config(bot) if bot else None
    user_settings = await bot_repo.get_user_settings(signal_row.user_id)
    open_trades = await bot_repo.count_open_trades(signal_row.bot_id)

    run_repo = AgentRunRepository()
    run_id = await run_repo.create(
        AgentRunInsert(
            user_id=signal_row.user_id,
            bot_id=signal_row.bot_id,
            run_status=AgentRunStatus.RUNNING.value,
            trigger_type="signal",
            started_at=utcnow_iso(),
            input_snapshot={"signal_id": str(signal_row.id), "symbol": signal_row.symbol},
        )
    )

    sanitized_meta, meta_suspicious, meta_oversize = sanitize_metadata(
        signal_row.metadata or {},
        signal_id=str(signal_row.id),
    )
    pipeline = await TradingPipeline.build()
    start = time.monotonic()

    try:
        state = await asyncio.wait_for(
            pipeline.run(
                signal=signal_row,
                bot=bot.model_dump() if bot else None,
                bot_config=config.model_dump() if config else None,
                user_settings=user_settings.model_dump() if user_settings else None,
                open_trade_count=open_trades,
                agent_run_id=run_id,
                sanitized_metadata=sanitized_meta,
                metadata_suspicious=meta_suspicious,
                metadata_oversize=meta_oversize,
            ),
            timeout=60,
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        print("debug.pipeline.completed")
        print(f"debug.final_decision={state.get('final_decision')}")
        print(f"debug.approval_status={state.get('approval_status')}")
        print(f"debug.effective_direction={state.get('effective_direction')}")
        print(f"debug.agent_results={len(state.get('agent_results', []))}")
        print(f"debug.duration_ms={duration_ms}")
        await run_repo.update_status(
            run_id=run_id,
            status=AgentRunStatus.COMPLETED.value,
            completed_at=utcnow_iso(),
            duration_ms=duration_ms,
            final_summary={
                "debug": True,
                "final_decision": state.get("final_decision"),
                "approval_status": state.get("approval_status"),
            },
        )
        return 0
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        message = str(exc).encode("ascii", "backslashreplace").decode("ascii")
        print("debug.pipeline.failed")
        print(f"debug.exception={message}")
        await run_repo.update_status(
            run_id=run_id,
            status=AgentRunStatus.FAILED.value,
            completed_at=utcnow_iso(),
            duration_ms=duration_ms,
            error_message=message[:500],
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
