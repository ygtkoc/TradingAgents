-- ─────────────────────────────────────────────────────────────────────────────
-- Migration 0008 — Paper account user-level controls
--
-- Adds:
--   • paper_accounts.status         enum-text  inactive | active | paused
--   • paper_accounts.started_at     timestamptz
--   • paper_accounts.paused_at      timestamptz
--   • paper_accounts.reset_at       timestamptz
--
-- Backfill: existing accounts → status='active' so the first cohort keeps
--           trading. New accounts default to 'inactive' so the user must
--           explicitly start their first paper-trading session.
--
-- Signal generator (autonomous/src/services/signal_generator/generator.py)
-- consults `status='active'` per user before seeding signals — this gives
-- per-user start / pause control on top of the global kill switch.
-- ─────────────────────────────────────────────────────────────────────────────
begin;

alter table public.paper_accounts
    add column if not exists status     text        not null default 'inactive',
    add column if not exists started_at timestamptz,
    add column if not exists paused_at  timestamptz,
    add column if not exists reset_at   timestamptz;

-- Allowed values
do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'paper_accounts_status_check'
  ) then
    alter table public.paper_accounts
      add constraint paper_accounts_status_check
      check (status in ('inactive', 'active', 'paused'));
  end if;
end$$;

create index if not exists paper_accounts_status_idx on public.paper_accounts (status);

-- Backfill: any pre-existing accounts default to active so the running
-- autonomous service does not silently stall.
update public.paper_accounts
   set status = 'active', started_at = coalesce(started_at, created_at)
 where status is null
    or status not in ('inactive', 'active', 'paused');

commit;
