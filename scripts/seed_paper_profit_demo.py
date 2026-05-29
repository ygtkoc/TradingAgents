#!/usr/bin/env python
"""
One-off dev seed for showing active paper bots with controlled fake trades.

The script is intentionally scoped to paper-mode active bots and marks every row
it creates with metadata.source = "one_off_paper_profit_demo". Re-running it
first removes only those tagged rows, then recreates a fresh snapshot.

USAGE:
    python scripts/seed_paper_profit_demo.py --yes
    python scripts/seed_paper_profit_demo.py --env autonomous/.env --yes
    python scripts/seed_paper_profit_demo.py --user-id <uuid> --yes
    python scripts/seed_paper_profit_demo.py --scenario mixed --user-id <uuid> --yes
"""
from __future__ import annotations

import argparse
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

SOURCE = "one_off_paper_profit_demo"
BASE_BALANCE = 1000.0
MIN_PROFIT = 40.0
MAX_PROFIT = 50.0
DEFAULT_RESERVE = 20.0


def _load_env(env_path: Path | None) -> tuple[str, str]:
    if env_path and env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        sys.stderr.write("missing SUPABASE_URL and/or SUPABASE_SERVICE_ROLE_KEY\n")
        sys.exit(2)
    return url, key


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _normalize_symbol(symbol: str) -> str:
    return symbol.replace("/", "").replace("-", "").upper()


def _display_symbol(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if "/" in symbol:
        return symbol
    if symbol.endswith("USDT") and len(symbol) > 4:
        return f"{symbol[:-4]}/USDT"
    if symbol.endswith("USD") and len(symbol) > 3:
        return f"{symbol[:-3]}/USD"
    return symbol


def _symbol_for_bot(bot: dict[str, Any]) -> str:
    pairs = bot.get("trading_pairs") or []
    if isinstance(pairs, list) and pairs:
        return _display_symbol(str(pairs[0]))
    base = str(bot.get("base_currency") or "BTC").upper()
    quote = str(bot.get("quote_currency") or "USDT").upper()
    if base in {"USD", "USDT"}:
        base = "BTC"
    return f"{base}/{quote}"


def _fallback_price(symbol: str) -> float:
    normalized = _normalize_symbol(symbol)
    if normalized.startswith("BTC"):
        return 108_000.0
    if normalized.startswith("ETH"):
        return 3_900.0
    if normalized.startswith("SOL"):
        return 165.0
    if normalized.startswith("BNB"):
        return 690.0
    if normalized.startswith("XRP"):
        return 2.25
    return 100.0


def _latest_price(symbol: str) -> float:
    normalized = _normalize_symbol(symbol)
    try:
        with urlopen(
            f"https://api.binance.com/api/v3/ticker/price?symbol={normalized}",
            timeout=5,
        ) as response:
            payload = response.read().decode("utf-8")
        # Tiny dependency-free parse for {"symbol":"BTCUSDT","price":"..."}.
        marker = '"price":"'
        if marker in payload:
            start = payload.index(marker) + len(marker)
            end = payload.index('"', start)
            price = float(payload[start:end])
            if price > 0:
                return price
    except (OSError, URLError, ValueError):
        pass
    return _fallback_price(symbol)


def _profit_targets(count: int) -> list[float]:
    offsets = [-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5]
    profits = [45.0 + offsets[index % len(offsets)] for index in range(count)]
    delta = round((45.0 * count) - sum(profits), 2)
    cursor = 0
    while abs(delta) >= 0.01 and profits:
        step = 1.0 if delta > 0 else -1.0
        next_value = profits[cursor] + step
        if MIN_PROFIT <= next_value <= MAX_PROFIT:
            profits[cursor] = next_value
            delta = round(delta - step, 2)
        cursor = (cursor + 1) % len(profits)
    return profits


def _mixed_trade_plan() -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for pnl in [42.0, 43.0, 44.0, 45.0, 46.0, 47.0, 48.0, 49.0]:
        plan.append({
            "status": "closed",
            "close_reason": "take_profit",
            "event_type": "take_profit_triggered",
            "target_pnl": pnl,
            "label": "take_profit",
        })
    for pnl in [-18.0, -20.0, -22.0, -24.0]:
        plan.append({
            "status": "closed",
            "close_reason": "stop_loss",
            "event_type": "stop_loss_triggered",
            "target_pnl": pnl,
            "label": "stopped",
        })
    for pnl in [40.0, 41.0, 42.0, 43.0, 44.0, 45.0, 46.0, 47.0, 48.0, 49.0]:
        plan.append({
            "status": "open",
            "close_reason": None,
            "event_type": "paper_trade_opened",
            "target_pnl": pnl,
            "label": "open_profit",
        })
    for pnl in [-10.0, -12.0]:
        plan.append({
            "status": "open",
            "close_reason": None,
            "event_type": "paper_trade_opened",
            "target_pnl": pnl,
            "label": "open_loss",
        })
    return plan


def _select_all(query) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    page = 1000
    while True:
        result = query.range(start, start + page - 1).execute()
        batch = result.data or []
        rows.extend(batch)
        if len(batch) < page:
            return rows
        start += page


def _delete_seed_rows(client, user_ids: set[str]) -> None:
    # Delete children before parents. These filters intentionally match only
    # rows created by this script.
    for table in ("paper_account_events", "trade_events"):
        query = client.table(table).delete().eq("metadata->>source", SOURCE)
        if user_ids:
            query = query.in_("user_id", sorted(user_ids))
        query.execute()

    query = client.table("trade_decisions").update({"linked_trade_id": None}).eq(
        "metadata->>source", SOURCE
    )
    if user_ids:
        query = query.in_("user_id", sorted(user_ids))
    query.execute()

    for table in ("trades", "trade_decisions", "agent_runs", "signals"):
        query = client.table(table).delete().eq("metadata->>source", SOURCE)
        if user_ids:
            query = query.in_("user_id", sorted(user_ids))
        query.execute()


def _get_or_create_account(client, user_id: str) -> dict[str, Any]:
    result = (
        client.table("paper_accounts")
        .select("*")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]

    created = (
        client.table("paper_accounts")
        .insert({
            "user_id": user_id,
            "currency": "USD",
            "starting_balance": BASE_BALANCE,
            "balance": BASE_BALANCE,
            "realized_pnl": 0,
            "unrealized_pnl": 0,
            "status": "active",
            "is_active": True,
            "started_at": _iso(_now()),
            "metadata": {"source": SOURCE, "note": "created by paper profit demo seed"},
        })
        .execute()
    )
    return created.data[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", type=Path, default=Path("autonomous/.env"))
    parser.add_argument("--user-id", help="limit seeding to one user")
    parser.add_argument(
        "--scenario",
        choices=["open-profit", "mixed"],
        default="open-profit",
        help="open-profit seeds one open winner per bot; mixed seeds TP/SL/open winners/open losers",
    )
    parser.add_argument("--yes", action="store_true", help="skip confirmation")
    parser.add_argument("--include-shadow", action="store_true", help="also seed shadow bots")
    args = parser.parse_args()

    url, key = _load_env(args.env)

    if not args.yes:
        print(f"This will seed fake paper profit demo data on {url}.")
        print("Type 'seed' to continue: ", end="", flush=True)
        if (sys.stdin.readline() or "").strip() != "seed":
            print("aborted.")
            return

    from supabase import create_client  # type: ignore

    random.seed(45)
    client = create_client(url, key)

    modes = ["paper", "shadow"] if args.include_shadow else ["paper"]
    bot_query = (
        client.table("bots")
        .select("*")
        .eq("status", "active")
        .eq("is_archived", False)
        .in_("mode", modes)
        .order("created_at", desc=False)
    )
    if args.user_id:
        bot_query = bot_query.eq("user_id", args.user_id)
    bots = _select_all(bot_query)

    if not bots:
        print("No active paper bots found; nothing seeded.")
        return

    user_ids = {str(bot["user_id"]) for bot in bots}
    _delete_seed_rows(client, user_ids)

    now = _now()
    total_profit_by_user: dict[str, float] = {user_id: 0.0 for user_id in user_ids}
    realized_by_user: dict[str, float] = {user_id: 0.0 for user_id in user_ids}
    reserve_by_user: dict[str, float] = {user_id: 0.0 for user_id in user_ids}
    created_trades = 0
    trade_plan = (
        _mixed_trade_plan()
        if args.scenario == "mixed"
        else [{"status": "open", "close_reason": None, "event_type": "paper_trade_opened", "target_pnl": pnl, "label": "open_profit"} for pnl in _profit_targets(len(bots))]
    )

    for index, plan_item in enumerate(trade_plan):
        bot = bots[index % len(bots)]
        user_id = str(bot["user_id"])
        bot_id = str(bot["id"])
        symbol = _symbol_for_bot(bot)
        current_price = _latest_price(symbol)
        target_pnl = float(plan_item["target_pnl"])
        abs_pnl = abs(target_pnl)
        direction = "long" if index % 4 != 1 else "short"
        side = "buy" if direction == "long" else "sell"
        move_pct = 0.03
        notional = round(abs_pnl / move_pct, 8)
        quantity = round(notional / current_price, 8)
        if quantity <= 0:
            quantity = 1.0

        entry_price = (
            current_price - (target_pnl / quantity)
            if direction == "long"
            else current_price + (target_pnl / quantity)
        )
        entry_price = round(entry_price, 8)
        stop_loss = round(entry_price * (0.985 if direction == "long" else 1.015), 8)
        take_profit = round(entry_price * (1.06 if direction == "long" else 0.94), 8)
        exit_price = (
            round(entry_price + (target_pnl / quantity), 8)
            if direction == "long"
            else round(entry_price - (target_pnl / quantity), 8)
        )
        pnl_pct = round((target_pnl / (entry_price * quantity)) * 100, 4)
        opened_at = now - timedelta(hours=24 - min(index, 23), minutes=7)
        completed_at = opened_at + timedelta(seconds=18)
        is_open = plan_item["status"] == "open"
        closed_at = None if is_open else completed_at + timedelta(hours=2)
        lifecycle_status = "monitoring" if is_open else "closed"

        agent_run = (
            client.table("agent_runs")
            .insert({
                "user_id": user_id,
                "bot_id": bot_id,
                "run_status": "completed",
                "trigger_type": "scheduled",
                "started_at": _iso(opened_at),
                "completed_at": _iso(completed_at),
                "duration_ms": 18_000,
                "input_snapshot": {
                    "source": SOURCE,
                    "symbol": symbol,
                    "latest_price": current_price,
                },
                "final_summary": {
                    "decision": f"open_{direction}",
                    "confidence": 0.87,
                    "expected_pnl": target_pnl,
                },
                "metadata": {
                    "source": SOURCE,
                    "note": "fake completed run for one-off paper profit demo",
                },
                "created_at": _iso(opened_at),
            })
            .execute()
            .data[0]
        )

        decision = (
            client.table("trade_decisions")
            .insert({
                "user_id": user_id,
                "bot_id": bot_id,
                "agent_run_id": agent_run["id"],
                "exchange": "binance",
                "symbol": symbol,
                "direction": direction,
                "mode": bot.get("mode") or "paper",
                "final_decision": f"open_{direction}",
                "score_summary": {
                    "aggregated_score": 88,
                    "confidence": 0.87,
                    "reasoning": "Seeded consensus approval for a one-off demo snapshot.",
                },
                "risk_summary": {
                    "risk_amount": DEFAULT_RESERVE,
                    "risk_percent": 2,
                    "risk_reward_ratio": 2.25,
                    "expected_reward": abs_pnl,
                    "entry_price": entry_price,
                    "quantity": quantity,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                    "sizing_model": "demo_seed",
                },
                "security_summary": {"vetoed": False, "injection_detected": False},
                "veto_summary": {"vetoed": False, "reason": None},
                "agent_outputs_snapshot": {
                    "data_agent": {"decision": f"open_{direction}", "confidence": 0.86},
                    "analysis_agent": {"decision": f"open_{direction}", "confidence": 0.89},
                    "risk_agent": {"decision": f"open_{direction}", "confidence": 0.84},
                    "security_agent": {"decision": "approve", "confidence": 0.93},
                },
                "approval_status": "approved",
                "manual_approval_required": False,
                "approved_by": user_id,
                "approved_at": _iso(completed_at),
                "suggested_entry_price": entry_price,
                "suggested_quantity": quantity,
                "suggested_stop_loss": stop_loss,
                "suggested_take_profit": take_profit,
                "execution_status": "executed",
                "execution_started_at": _iso(completed_at),
                "execution_completed_at": _iso(completed_at + timedelta(seconds=2)),
                "metadata": {
                    "source": SOURCE,
                    "target_pnl": target_pnl,
                    "scenario": args.scenario,
                    "scenario_label": plan_item["label"],
                    "current_price_at_seed": current_price,
                    "fake_demo": True,
                },
                "created_at": _iso(opened_at),
            })
            .execute()
            .data[0]
        )

        trade = (
            client.table("trades")
            .insert({
                "user_id": user_id,
                "bot_id": bot_id,
                "trade_decision_id": decision["id"],
                "mode": bot.get("mode") or "paper",
                "exchange": "binance",
                "symbol": symbol,
                "side": side,
                "direction": direction,
                "status": plan_item["status"],
                "entry_price": entry_price,
                "avg_entry_price": entry_price,
                "exit_price": None if is_open else exit_price,
                "avg_exit_price": None if is_open else exit_price,
                "quantity": quantity,
                "filled_quantity": quantity,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "realized_pnl": 0 if is_open else target_pnl,
                "unrealized_pnl": target_pnl if is_open else None,
                "pnl_pct": pnl_pct,
                "risk_amount": DEFAULT_RESERVE,
                "risk_percent": 2,
                "risk_reward_ratio": 2.25,
                "expected_reward": abs_pnl,
                "notional": round(entry_price * quantity, 8),
                "close_reason": plan_item["close_reason"],
                "lifecycle_status": lifecycle_status,
                "lifecycle_last_checked_at": _iso(now),
                "trailing_stop_price": stop_loss,
                "highest_price_seen": current_price if direction == "long" else None,
                "lowest_price_seen": current_price if direction == "short" else None,
                "opened_at": _iso(opened_at),
                "closed_at": None if closed_at is None else _iso(closed_at),
                "last_updated_at": _iso(now),
                "metadata": {
                    "source": SOURCE,
                    "scenario": args.scenario,
                    "scenario_label": plan_item["label"],
                    "simulated": True,
                    "paper_execution": True,
                    "paper_fill_status": "filled",
                    "reserved_on_open": True,
                    "reserved_amount": DEFAULT_RESERVE if is_open else 0,
                    "target_pnl": target_pnl,
                    "latest_price": current_price,
                    "fake_demo": True,
                },
                "created_at": _iso(opened_at),
            })
            .execute()
            .data[0]
        )

        client.table("trade_decisions").update({"linked_trade_id": trade["id"]}).eq(
            "id", decision["id"]
        ).execute()
        client.table("agent_runs").update({"trade_decision_id": decision["id"]}).eq(
            "id", agent_run["id"]
        ).execute()

        client.table("trade_events").insert({
            "trade_id": trade["id"],
            "trade_decision_id": decision["id"],
            "bot_id": bot_id,
            "user_id": user_id,
            "event_type": "paper_trade_opened",
            "details": {
                "source": SOURCE,
                "scenario": args.scenario,
                "scenario_label": plan_item["label"],
                "fill_price": entry_price,
                "filled_qty": quantity,
                "target_pnl": target_pnl,
                "current_price_at_seed": current_price,
            },
            "metadata": {"source": SOURCE, "fake_demo": True},
            "created_at": _iso(completed_at + timedelta(seconds=3)),
        }).execute()

        if is_open:
            total_profit_by_user[user_id] += target_pnl
            reserve_by_user[user_id] += DEFAULT_RESERVE
        else:
            realized_by_user[user_id] += target_pnl
            client.table("trade_events").insert({
                "trade_id": trade["id"],
                "trade_decision_id": decision["id"],
                "bot_id": bot_id,
                "user_id": user_id,
                "event_type": plan_item["event_type"],
                "details": {
                    "source": SOURCE,
                    "scenario": args.scenario,
                    "scenario_label": plan_item["label"],
                    "exit_price": exit_price,
                    "realized_pnl": target_pnl,
                    "pnl_pct": pnl_pct,
                },
                "metadata": {"source": SOURCE, "fake_demo": True, "scenario": args.scenario},
                "created_at": _iso(closed_at or now),
            }).execute()
        created_trades += 1

    for user_id, total_profit in total_profit_by_user.items():
        account = _get_or_create_account(client, user_id)
        reserved = reserve_by_user[user_id]
        realized = realized_by_user[user_id]
        balance = round(BASE_BALANCE + realized, 8)
        client.table("paper_accounts").update({
            "starting_balance": BASE_BALANCE,
            "balance": balance,
            "reserved_balance": reserved,
            "realized_pnl": round(realized, 8),
            "unrealized_pnl": round(total_profit, 8),
            "status": "active",
            "is_active": True,
            "started_at": _iso(now),
            "paused_at": None,
            "metadata": {
                **(account.get("metadata") or {}),
                "source": SOURCE,
                "fake_demo": True,
                "scenario": args.scenario,
                "seeded_open_trades": sum(
                    1
                    for index, item in enumerate(trade_plan)
                    if item["status"] == "open" and str(bots[index % len(bots)]["user_id"]) == user_id
                ),
                "seeded_closed_trades": sum(
                    1
                    for index, item in enumerate(trade_plan)
                    if item["status"] == "closed" and str(bots[index % len(bots)]["user_id"]) == user_id
                ),
                "seeded_realized_pnl": round(realized, 2),
                "seeded_unrealized_pnl": round(total_profit, 2),
            },
        }).eq("id", account["id"]).execute()

        client.table("paper_account_events").insert({
            "account_id": account["id"],
            "user_id": user_id,
            "trade_id": None,
            "event_type": "demo_unrealized_profit_seed",
            "delta": 0,
            "realized_delta": 0,
            "unrealized_delta": round(total_profit, 8),
            "balance_after": balance,
            "realized_after": round(realized, 8),
            "unrealized_after": round(total_profit, 8),
            "note": f"one-off fake {args.scenario} demo seed",
            "metadata": {
                "source": SOURCE,
                "scenario": args.scenario,
                "reserved_balance": reserved,
                "equity_after": round(balance + total_profit, 8),
                "fake_demo": True,
            },
            "created_at": _iso(now),
        }).execute()

    total_profit = round(sum(total_profit_by_user.values()), 2)
    total_realized = round(sum(realized_by_user.values()), 2)
    print(
        f"Seeded {created_trades} {args.scenario} trades across {len(user_ids)} user(s). "
        f"Realized PnL: ${total_realized:.2f}; unrealized PnL: ${total_profit:.2f}; "
        f"display equity baseline: ${BASE_BALANCE + total_realized + total_profit:.2f}."
    )


if __name__ == "__main__":
    main()
