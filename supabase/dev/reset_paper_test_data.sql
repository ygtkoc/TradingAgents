-- ─────────────────────────────────────────────────────────────────────────────
-- DEV RESET — paper trading test data
--
-- ⚠️  DESTRUCTIVE.  Run only against a development / staging database.
-- Wipes runtime state so a fresh autonomous paper-trading cycle starts clean.
--
-- DELETES:
--   • signals
--   • trade_decisions
--   • trade_events
--   • trades
--   • agent_runs
--   • agent_outputs
--   • risk_logs
--   • security_logs
--   • audit_logs
--   • market_snapshots
--   • paper_account_events     (added in migration 0007)
--   • paper_accounts.balance reset to starting_balance, equity recomputed
--
-- KEEPS:
--   • auth.users / profiles / user_settings
--   • bots / bot_configs / exchange_accounts
--   • agent_definitions / platform_settings
--   • subscriptions / plans
-- ─────────────────────────────────────────────────────────────────────────────
begin;

-- Order matters: child tables before parents (FK cascade safety).
truncate table public.trade_events           restart identity cascade;
truncate table public.trades                 restart identity cascade;
truncate table public.trade_decisions        restart identity cascade;
truncate table public.agent_outputs          restart identity cascade;
truncate table public.agent_runs             restart identity cascade;
truncate table public.signals                restart identity cascade;
truncate table public.risk_logs              restart identity cascade;
truncate table public.security_logs          restart identity cascade;
truncate table public.audit_logs             restart identity cascade;
truncate table public.market_snapshots       restart identity cascade;

-- Paper accounts (only if migration 0007 has been applied)
do $$
begin
  if to_regclass('public.paper_account_events') is not null then
    truncate table public.paper_account_events restart identity cascade;
  end if;

  if to_regclass('public.paper_accounts') is not null then
    update public.paper_accounts
       set balance         = starting_balance,
           realized_pnl    = 0,
           unrealized_pnl  = 0,
           equity          = starting_balance,
           updated_at      = now();
  end if;
end$$;

-- Reset bot lifecycle counters so the position engine starts fresh.
update public.bots
   set updated_at = now();

commit;

-- Confirmation report
select 'signals'           as table, count(*) from public.signals
union all select 'trade_decisions',  count(*) from public.trade_decisions
union all select 'trades',           count(*) from public.trades
union all select 'agent_runs',       count(*) from public.agent_runs
union all select 'market_snapshots', count(*) from public.market_snapshots;
