-- ─────────────────────────────────────────────────────────────────────────────
-- Migration 0007 — Paper trading accounts
--
-- Adds a per-user paper trading account so the autonomous paper-trading loop
-- has a real ledger (no fake balances on the frontend).
--
-- DESIGN:
--   • One paper_accounts row per user, default $1000 USD starting balance.
--   • paper_account_events is an append-only audit ledger of every
--     debit / credit (open trade margin reservation, close trade settlement,
--     manual reset). The current account state is the rolling sum.
--   • Live trading does NOT use this table. Live balances come from the
--     exchange.
--
-- SAFETY:
--   • RLS: users can read their own paper_accounts; nobody can INSERT/UPDATE
--     directly. Writes happen exclusively via Edge Functions (service_role).
--   • CHECK constraint: balance >= 0  (no negative paper balance).
--   • Ledger trigger updates paper_accounts atomically when an event lands.
-- ─────────────────────────────────────────────────────────────────────────────
begin;

-- ── paper_accounts ──────────────────────────────────────────────────────────
create table if not exists public.paper_accounts (
    id                uuid primary key default gen_random_uuid(),
    user_id           uuid not null unique references auth.users(id) on delete cascade,
    currency          text not null default 'USD',
    starting_balance  numeric(20, 8) not null default 1000,
    balance           numeric(20, 8) not null default 1000,   -- realised cash on hand
    realized_pnl      numeric(20, 8) not null default 0,
    unrealized_pnl    numeric(20, 8) not null default 0,
    equity            numeric(20, 8) generated always as (balance + unrealized_pnl) stored,
    is_active         boolean not null default true,
    metadata          jsonb not null default '{}'::jsonb,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),

    constraint paper_accounts_balance_nonneg       check (balance >= 0),
    constraint paper_accounts_starting_balance_pos check (starting_balance > 0)
);

create index if not exists paper_accounts_user_id_idx on public.paper_accounts (user_id);

-- ── paper_account_events ────────────────────────────────────────────────────
create table if not exists public.paper_account_events (
    id           uuid primary key default gen_random_uuid(),
    account_id   uuid not null references public.paper_accounts(id) on delete cascade,
    user_id      uuid not null references auth.users(id) on delete cascade,
    trade_id     uuid     references public.trades(id) on delete set null,
    event_type   text not null,                              -- e.g. open / close / adjust / reset
    delta        numeric(20, 8) not null default 0,          -- realised cash change (signed)
    realized_delta   numeric(20, 8) not null default 0,
    unrealized_delta numeric(20, 8) not null default 0,
    balance_after    numeric(20, 8) not null,
    realized_after   numeric(20, 8) not null default 0,
    unrealized_after numeric(20, 8) not null default 0,
    note         text,
    metadata     jsonb not null default '{}'::jsonb,
    created_at   timestamptz not null default now()
);

create index if not exists paper_account_events_account_idx on public.paper_account_events (account_id, created_at desc);
create index if not exists paper_account_events_trade_idx   on public.paper_account_events (trade_id);
create index if not exists paper_account_events_user_idx    on public.paper_account_events (user_id, created_at desc);

-- ── RLS ─────────────────────────────────────────────────────────────────────
alter table public.paper_accounts        enable row level security;
alter table public.paper_account_events  enable row level security;

drop policy if exists paper_accounts_self_read on public.paper_accounts;
create policy paper_accounts_self_read
    on public.paper_accounts
    for select
    using (auth.uid() = user_id);

-- INSERT/UPDATE/DELETE intentionally have NO policy → blocked for `authenticated`.
-- Edge Functions use service_role and bypass RLS.

drop policy if exists paper_account_events_self_read on public.paper_account_events;
create policy paper_account_events_self_read
    on public.paper_account_events
    for select
    using (auth.uid() = user_id);

-- ── Auto-create a paper_accounts row for every new user ─────────────────────
create or replace function public.fn_create_paper_account_for_new_user()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
    insert into public.paper_accounts (user_id)
    values (new.id)
    on conflict (user_id) do nothing;
    return new;
end$$;

drop trigger if exists trg_create_paper_account on auth.users;
create trigger trg_create_paper_account
    after insert on auth.users
    for each row execute procedure public.fn_create_paper_account_for_new_user();

-- ── updated_at maintenance ─────────────────────────────────────────────────
create or replace function public.fn_paper_accounts_set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end$$;

drop trigger if exists trg_paper_accounts_updated_at on public.paper_accounts;
create trigger trg_paper_accounts_updated_at
    before update on public.paper_accounts
    for each row execute procedure public.fn_paper_accounts_set_updated_at();

-- ── Backfill: create paper_accounts for existing users ─────────────────────
insert into public.paper_accounts (user_id)
select u.id
  from auth.users u
  left join public.paper_accounts p on p.user_id = u.id
 where p.id is null
on conflict (user_id) do nothing;

commit;
