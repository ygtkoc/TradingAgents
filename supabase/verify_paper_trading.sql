-- ─────────────────────────────────────────────────────────────────────────────
-- Paper Trading System Verification Script
--
-- Run against your local Supabase instance:
--   psql postgresql://postgres:postgres@localhost:54322/postgres -f verify_paper_trading.sql
--
-- Or via the Supabase dashboard SQL editor.
-- ─────────────────────────────────────────────────────────────────────────────

-- ── 1. Schema health ─────────────────────────────────────────────────────────

select '=== PAPER ACCOUNTS SCHEMA ===' as check;

select
  column_name,
  data_type,
  is_nullable,
  column_default
from information_schema.columns
where table_schema = 'public'
  and table_name   = 'paper_accounts'
order by ordinal_position;

-- Expected columns (from migrations 0007 + 0008):
--   id, user_id, currency, starting_balance, balance, realized_pnl,
--   unrealized_pnl, equity (generated), is_active, metadata, created_at,
--   updated_at, status, started_at, paused_at, reset_at

-- ── 2. RLS policies ──────────────────────────────────────────────────────────

select '=== PAPER ACCOUNTS RLS POLICIES ===' as check;

select
  policyname,
  cmd,
  roles,
  qual,
  with_check
from pg_policies
where tablename = 'paper_accounts'
order by policyname;

-- Expected policies:
--   paper_accounts_self_read   → SELECT for authenticated (auth.uid() = user_id)
--   paper_accounts_self_insert → INSERT for authenticated (0010 migration)
--   paper_accounts_self_update → UPDATE for authenticated (0010 migration)

-- ── 3. Table grants ──────────────────────────────────────────────────────────

select '=== TABLE GRANTS ===' as check;

select
  grantee,
  table_name,
  privilege_type
from information_schema.role_table_grants
where table_name in ('paper_accounts', 'paper_account_events', 'bots', 'signals')
  and grantee in ('authenticated', 'service_role')
order by table_name, grantee, privilege_type;

-- ── 4. Paper accounts data ────────────────────────────────────────────────────

select '=== PAPER ACCOUNTS (existing rows) ===' as check;

select
  id,
  user_id,
  status,
  balance,
  starting_balance,
  equity,
  realized_pnl,
  unrealized_pnl,
  started_at,
  created_at
from public.paper_accounts
order by created_at desc
limit 20;

-- ── 5. Active paper bots ──────────────────────────────────────────────────────

select '=== ACTIVE PAPER BOTS ===' as check;

select
  id,
  user_id,
  name,
  exchange,
  trading_pairs,
  strategy,
  mode,
  status,
  created_at
from public.bots
where mode    = 'paper'
  and status  = 'active'
  and is_archived = false
order by created_at desc;

-- ── 6. Recent signals ─────────────────────────────────────────────────────────

select '=== RECENT SIGNALS (last 20) ===' as check;

select
  id,
  bot_id,
  symbol,
  direction,
  signal_type,
  status,
  created_at
from public.signals
order by created_at desc
limit 20;

-- ── 7. Recent trade decisions ─────────────────────────────────────────────────

select '=== RECENT TRADE DECISIONS (last 20) ===' as check;

select
  id,
  bot_id,
  symbol,
  direction,
  final_decision,
  approval_status,
  execution_status,
  score_summary->>'aggregated_score' as score,
  score_summary->>'confidence'       as confidence,
  created_at
from public.trade_decisions
order by created_at desc
limit 20;

-- ── 8. Recent trades ─────────────────────────────────────────────────────────

select '=== RECENT TRADES (last 20) ===' as check;

select
  id,
  bot_id,
  symbol,
  side,
  mode,
  status,
  entry_price,
  quantity,
  realized_pnl,
  unrealized_pnl,
  lifecycle_status,
  created_at
from public.trades
order by created_at desc
limit 20;

-- ── 9. Recent market snapshots ─────────────────────────────────────────────

select '=== RECENT MARKET SNAPSHOTS (last 10 per symbol) ===' as check;

select distinct on (symbol)
  id,
  symbol,
  timeframe,
  close_price,
  volume,
  captured_at
from public.market_snapshots
order by symbol, captured_at desc;

-- ── 10. Platform settings ─────────────────────────────────────────────────────

select '=== PLATFORM SETTINGS ===' as check;

select key, value, updated_at
from public.platform_settings
order by key;

-- Expected: global_trading_enabled = true (unless you've flipped the kill switch)

-- ── 11. Signal / decision pipeline counts ────────────────────────────────────

select '=== PIPELINE COUNTS (last 24h) ===' as check;

select
  'signals'         as entity,
  count(*)          as total,
  sum(case when status = 'pending'    then 1 else 0 end) as pending,
  sum(case when status = 'processing' then 1 else 0 end) as processing,
  sum(case when status = 'completed'  then 1 else 0 end) as completed,
  sum(case when status = 'failed'     then 1 else 0 end) as failed
from public.signals
where created_at > now() - interval '24 hours'

union all

select
  'trade_decisions',
  count(*),
  sum(case when approval_status = 'pending'       then 1 else 0 end),
  sum(case when approval_status = 'auto_approved' then 1 else 0 end),
  sum(case when approval_status = 'rejected'      then 1 else 0 end),
  0
from public.trade_decisions
where created_at > now() - interval '24 hours'

union all

select
  'trades',
  count(*),
  sum(case when status = 'open'   then 1 else 0 end),
  sum(case when status = 'closed' then 1 else 0 end),
  0,
  0
from public.trades
where created_at > now() - interval '24 hours';

-- ── 12. Auto-create trigger ──────────────────────────────────────────────────

select '=== PAPER ACCOUNT AUTO-CREATE TRIGGER ===' as check;

select
  trigger_name,
  event_manipulation,
  event_object_table,
  action_timing,
  action_orientation
from information_schema.triggers
where trigger_name = 'trg_create_paper_account';

-- Should show: trg_create_paper_account, INSERT, users, AFTER, ROW

-- ── 13. Quick health summary ─────────────────────────────────────────────────

select '=== HEALTH SUMMARY ===' as check;

select
  (select count(*) from public.paper_accounts where status = 'active')     as active_paper_accounts,
  (select count(*) from public.bots where mode = 'paper' and status = 'active' and is_archived = false) as active_paper_bots,
  (select count(*) from public.signals where created_at > now() - interval '1 hour')  as signals_last_hour,
  (select count(*) from public.trade_decisions where created_at > now() - interval '1 hour') as decisions_last_hour,
  (select count(*) from public.trades where status = 'open' and mode = 'paper')         as open_paper_trades,
  (select count(*) from public.market_snapshots where captured_at > now() - interval '5 minutes') as fresh_snapshots;

-- If signals_last_hour = 0, check:
--   • autonomous service is running (python scripts/dev_autonomous.py)
--   • kill switch is ON (global_trading_enabled = true)
--   • paper account status = 'active'
--   • market data feed is healthy (check /health endpoint)

-- If decisions_last_hour = 0 but signals > 0, check:
--   • agent-engine is running
--   • OPENAI_API_KEY is set in agent-engine .env

-- If open_paper_trades = 0 but decisions > 0, check:
--   • execution-engine is running
--   • trade_decisions have approval_status = 'auto_approved'
--   • paper account has sufficient balance
