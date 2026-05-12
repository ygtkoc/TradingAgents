-- ─────────────────────────────────────────────────────────────────────────────
-- Migration 0009 — Allow authenticated users to manage their own bots
--
-- The customer UI creates / edits bots directly (RLS-scoped). Trading-critical
-- writes (trades, trade_decisions, signals, agent_*) remain locked down — only
-- the engines write those.
--
-- Policies are added with `if not exists` semantics via pg_policies guard
-- so the migration is idempotent across re-runs.
-- ─────────────────────────────────────────────────────────────────────────────
begin;

-- Make sure RLS is on (no-op if already enabled)
alter table public.bots enable row level security;

-- 1) SELECT: a user can read their own bots
do $$
begin
  if not exists (
    select 1 from pg_policies
     where schemaname = 'public' and tablename = 'bots'
       and policyname = 'bots_select_own'
  ) then
    create policy bots_select_own on public.bots
      for select to authenticated
      using (auth.uid() = user_id);
  end if;
end$$;

-- 2) INSERT: a user can create rows for themselves only.
--    `mode='live'` is permitted at the row level, but the engines additionally
--    gate live execution with their own checks — RLS alone never enables a
--    real-money trade.
do $$
begin
  if not exists (
    select 1 from pg_policies
     where schemaname = 'public' and tablename = 'bots'
       and policyname = 'bots_insert_own'
  ) then
    create policy bots_insert_own on public.bots
      for insert to authenticated
      with check (auth.uid() = user_id);
  end if;
end$$;

-- 3) UPDATE: a user can edit their own rows. user_id is immutable
--    (the with-check forbids transferring to a different user).
do $$
begin
  if not exists (
    select 1 from pg_policies
     where schemaname = 'public' and tablename = 'bots'
       and policyname = 'bots_update_own'
  ) then
    create policy bots_update_own on public.bots
      for update to authenticated
      using      (auth.uid() = user_id)
      with check (auth.uid() = user_id);
  end if;
end$$;

-- 4) DELETE: soft delete only — frontend should set is_archived=true, but if
--    a user wants to truly delete a never-traded bot we allow it.
do $$
begin
  if not exists (
    select 1 from pg_policies
     where schemaname = 'public' and tablename = 'bots'
       and policyname = 'bots_delete_own'
  ) then
    create policy bots_delete_own on public.bots
      for delete to authenticated
      using (auth.uid() = user_id);
  end if;
end$$;

commit;
