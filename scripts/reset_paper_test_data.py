#!/usr/bin/env python
"""
Dev-only reset script for the autonomous paper-trading test data.

Wipes RUNTIME state (signals, decisions, trades, runs, logs, snapshots) and
resets paper account balances. NEVER touches users / bots / agent_definitions
/ platform_settings / subscriptions / plans.

USAGE:
    python scripts/reset_paper_test_data.py                  # uses ./autonomous/.env
    python scripts/reset_paper_test_data.py --env path/to/.env
    python scripts/reset_paper_test_data.py --yes            # skip confirmation
    python scripts/reset_paper_test_data.py --keep-snapshots # preserve market_snapshots

REQUIRES:
    SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the .env or environment.

This script intentionally REFUSES to run if the URL contains 'prod' (case-
insensitive) and you have not passed --i-know-what-im-doing.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# ── Tables wiped (children before parents) ──────────────────────────────────
RUNTIME_TABLES: list[str] = [
    "trade_events",
    "trade_decisions",
    "trades",
    "agent_outputs",
    "agent_runs",
    "signals",
    "risk_logs",
    "security_logs",
    "audit_logs",
]

# Optional tables — wiped only if they exist
OPTIONAL_TABLES: list[str] = [
    "paper_account_events",
]

# Tables we NEVER touch (whitelisted for clarity / docs)
PROTECTED_TABLES: list[str] = [
    "auth.users", "profiles", "user_settings",
    "bots", "bot_configs", "exchange_accounts",
    "agent_definitions", "platform_settings",
    "subscriptions", "plans",
]


def _load_env(env_path: Path | None) -> tuple[str, str]:
    if env_path and env_path.exists():
        # Minimal .env loader (no python-dotenv dependency required)
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)

    url  = os.environ.get("SUPABASE_URL")
    key  = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        sys.stderr.write("missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY\n")
        sys.exit(2)
    return url, key


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", type=Path, default=Path("autonomous/.env"))
    parser.add_argument("--yes", action="store_true", help="skip confirmation prompt")
    parser.add_argument("--keep-snapshots", action="store_true",
                        help="preserve market_snapshots (useful for debugging)")
    parser.add_argument("--i-know-what-im-doing", action="store_true",
                        help="bypass production-URL safety guard")
    args = parser.parse_args()

    url, key = _load_env(args.env)

    if "prod" in url.lower() and not args.i_know_what_im_doing:
        sys.stderr.write(
            f"REFUSING to reset against URL containing 'prod': {url}\n"
            f"Pass --i-know-what-im-doing to override.\n"
        )
        sys.exit(3)

    if not args.yes:
        sys.stdout.write(f"This will wipe runtime data on {url}.\n")
        sys.stdout.write("Type 'reset' to confirm: ")
        sys.stdout.flush()
        if (sys.stdin.readline() or "").strip() != "reset":
            sys.stdout.write("aborted.\n")
            sys.exit(0)

    # Lazy import so the script can show its --help even if supabase isn't installed
    from supabase import create_client    # type: ignore

    client = create_client(url, key)

    tables = list(RUNTIME_TABLES)
    if not args.keep_snapshots:
        tables.append("market_snapshots")

    deleted: dict[str, int] = {}
    for table in tables + OPTIONAL_TABLES:
        try:
            res = client.table(table).delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            n = len(res.data or []) if hasattr(res, "data") else 0
            deleted[table] = n
            print(f"[reset] {table:<24} {n:>6} rows")
        except Exception as exc:
            # OPTIONAL_TABLES may not exist; log and continue
            if table in OPTIONAL_TABLES:
                print(f"[reset] {table:<24} (skipped — table not present)")
                continue
            print(f"[reset] {table:<24} FAILED: {str(exc)[:200]}")

    # Reset paper accounts: balance ← starting_balance, pnls → 0
    try:
        # Read all paper_accounts then update each (no SQL function needed)
        accts = client.table("paper_accounts").select("id,starting_balance").execute().data or []
        for a in accts:
            client.table("paper_accounts").update({
                "balance":         a.get("starting_balance", 1000),
                "realized_pnl":    0,
                "unrealized_pnl":  0,
                "status":          "paused",
                "started_at":      None,
                "paused_at":       None,
            }).eq("id", a["id"]).execute()
        print(f"[reset] paper_accounts        {len(accts):>6} reset to starting_balance")
    except Exception as exc:
        print(f"[reset] paper_accounts        (skipped — {str(exc)[:120]})")

    print("\nProtected (untouched):")
    for t in PROTECTED_TABLES:
        print(f"  • {t}")

    print("\nDone.")


if __name__ == "__main__":
    main()
