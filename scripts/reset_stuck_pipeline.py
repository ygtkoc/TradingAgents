#!/usr/bin/env python
"""
Reset stuck pipeline state.

Sometimes during development the agent pipeline crashes mid-run, leaving:

  • signals.status        = 'processing'   (no worker still running)
  • agent_runs.run_status = 'running'      (no worker still running)
  • bots.lifecycle_status = 'monitoring'   (worker died holding the claim)

This script clears those stuck rows safely:

  • signals stuck in 'processing' for > --min-age-minutes are reset to 'pending'.
  • agent_runs stuck in 'running' / 'pending' for > --min-age-minutes are
    marked 'failed' with a clear error_message.
  • trades stuck in lifecycle_status 'monitoring' for > --min-age-minutes are
    reset to 'idle' so the position-engine reclaims them.

It NEVER deletes:
  • users / profiles / user_settings
  • bots (only their lifecycle_status field is touched, never bots.status)
  • exchange_accounts / agent_definitions / paper_accounts

USAGE:
    python scripts/reset_stuck_pipeline.py
    python scripts/reset_stuck_pipeline.py --min-age-minutes 1 --yes
    python scripts/reset_stuck_pipeline.py --env autonomous/.env --dry-run

REQUIRES:
    SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY (defaults read from autonomous/.env).
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _load_env(env_path: Path | None) -> tuple[str, str]:
    if env_path and env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        sys.stderr.write("missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY\n")
        sys.exit(2)
    return url, key


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", type=Path, default=Path("autonomous/.env"))
    parser.add_argument("--min-age-minutes", type=int, default=2,
                        help="rows must be at least this old to be reset (default 2)")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be reset without writing")
    parser.add_argument("--yes",     action="store_true", help="skip confirmation")
    parser.add_argument("--i-know-what-im-doing", action="store_true",
                        help="bypass production-URL safety guard")
    args = parser.parse_args()

    url, _ = _load_env(args.env)
    if "prod" in url.lower() and not args.i_know_what_im_doing:
        sys.stderr.write(f"REFUSING to run against URL containing 'prod': {url}\n")
        sys.exit(3)

    if not args.yes and not args.dry_run:
        sys.stdout.write(f"Reset stuck pipeline state on {url}? Type 'yes' to confirm: ")
        sys.stdout.flush()
        if (sys.stdin.readline() or "").strip().lower() != "yes":
            sys.stdout.write("aborted.\n")
            return

    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=args.min_age_minutes)).isoformat()

    from supabase import create_client    # type: ignore
    client = create_client(url, os.environ["SUPABASE_SERVICE_ROLE_KEY"])

    # ── 1. signals stuck in processing ──────────────────────────────────────
    sigs = (
        client.table("signals")
        .select("id,bot_id,symbol,processing_started_at")
        .eq("status", "processing")
        .lt("processing_started_at", cutoff)
        .limit(500)
        .execute()
        .data
        or []
    )
    print(f"[reset-stuck] signals stuck in 'processing' (> {args.min_age_minutes}m): {len(sigs)}")
    if sigs and not args.dry_run:
        for s in sigs:
            client.table("signals").update({
                "status":                "pending",
                "processing_worker_id":  None,
                "processing_started_at": None,
            }).eq("id", s["id"]).execute()
        print(f"[reset-stuck]   → reset to 'pending'")

    # ── 2. agent_runs stuck in running/pending ─────────────────────────────
    runs = (
        client.table("agent_runs")
        .select("id,bot_id,run_status,started_at")
        .in_("run_status", ["running", "pending"])
        .lt("started_at", cutoff)
        .limit(500)
        .execute()
        .data
        or []
    )
    print(f"[reset-stuck] agent_runs stuck in 'running'/'pending' (> {args.min_age_minutes}m): {len(runs)}")
    if runs and not args.dry_run:
        for r in runs:
            client.table("agent_runs").update({
                "run_status":   "failed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error_message": "Reset by reset_stuck_pipeline.py — pipeline did not finish.",
            }).eq("id", r["id"]).execute()
        print(f"[reset-stuck]   → marked 'failed'")

    # ── 3. trades stuck monitoring ─────────────────────────────────────────
    trades = (
        client.table("trades")
        .select("id,symbol,lifecycle_status,lifecycle_claimed_at")
        .eq("lifecycle_status", "monitoring")
        .lt("lifecycle_claimed_at", cutoff)
        .limit(500)
        .execute()
        .data
        or []
    )
    print(f"[reset-stuck] trades stuck 'monitoring' (> {args.min_age_minutes}m): {len(trades)}")
    if trades and not args.dry_run:
        for t in trades:
            client.table("trades").update({
                "lifecycle_status":     "idle",
                "lifecycle_worker_id":  None,
                "lifecycle_claimed_at": None,
                "lifecycle_last_checked_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", t["id"]).execute()
        print(f"[reset-stuck]   → reset to 'idle'")

    if args.dry_run:
        print("\n[reset-stuck] DRY-RUN — no rows modified.")
    else:
        print("\n[reset-stuck] Done.")


if __name__ == "__main__":
    main()
