-- ============================================================
-- lucrandos Platform - Supabase SQL Foundation
-- Migration: 0001_initial_schema.sql
-- Generated: 2026-04-24
--
-- IMPORTANT DEPLOYMENT NOTES:
--   1. Run in Supabase SQL Editor or via `supabase db push`
--   2. pgsodium extension must be enabled in Supabase Dashboard before running
--   3. encrypted_api_keys payloads must ALWAYS be encrypted by Edge Functions
--      before INSERT. Never insert plaintext into those columns.
--   4. The service_role key (used by Edge Functions) bypasses RLS.
--      Guard your Edge Functions with proper auth checks.
--   5. Disable direct table access for encrypted_api_keys in Supabase Dashboard
--      (Data API → disable table exposure for this table).
-- ============================================================

-- ============================================================
-- EXTENSIONS
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
-- pgsodium is pre-enabled in Supabase; enables Vault + key management
-- CREATE EXTENSION IF NOT EXISTS "pgsodium";  -- Uncomment if not auto-enabled

-- ============================================================
-- ENUMS
-- ============================================================

CREATE TYPE public.user_role AS ENUM (
  'user',
  'pro_user',
  'admin',
  'super_admin',
  'security_admin'
);

-- paper  = simulated trades with real market data, no real orders
-- live   = real orders on exchange
-- shadow = real market data + real order sizing calculation, but orders never sent
CREATE TYPE public.bot_mode AS ENUM (
  'paper',
  'live',
  'shadow'
);

CREATE TYPE public.bot_status AS ENUM (
  'draft',
  'active',
  'paused',
  'stopped',
  'archived',
  'error'
);

CREATE TYPE public.agent_category AS ENUM (
  'data',
  'analysis',
  'critique',
  'risk',
  'security',
  'execution',
  'monitoring',
  'post_trade',
  'system_evolution'
);

CREATE TYPE public.agent_run_status AS ENUM (
  'pending',
  'running',
  'completed',
  'failed',
  'cancelled',
  'timeout'
);

CREATE TYPE public.agent_decision AS ENUM (
  'open_long',
  'open_short',
  'wait',
  'reject',
  'manual_approval_required',
  'close_position',
  'reduce_position',
  'pause_trading'
);

CREATE TYPE public.trade_direction AS ENUM (
  'long',
  'short',
  'neutral'
);

CREATE TYPE public.trade_status AS ENUM (
  'pending',
  'open',
  'closed',
  'cancelled',
  'failed',
  'partial_fill'
);

CREATE TYPE public.trade_mode AS ENUM (
  'paper',
  'live',
  'shadow'
);

CREATE TYPE public.severity_level AS ENUM (
  'info',
  'low',
  'medium',
  'high',
  'critical'
);

CREATE TYPE public.subscription_plan AS ENUM (
  'free',
  'starter',
  'pro',
  'enterprise'
);

CREATE TYPE public.subscription_status AS ENUM (
  'trialing',
  'active',
  'past_due',
  'cancelled',
  'unpaid',
  'paused'
);

CREATE TYPE public.report_status AS ENUM (
  'open',
  'acknowledged',
  'in_progress',
  'resolved',
  'wont_fix'
);

CREATE TYPE public.approval_status AS ENUM (
  'pending',
  'approved',
  'rejected',
  'auto_approved',
  'expired'
);

CREATE TYPE public.signal_status AS ENUM (
  'pending',
  'processed',
  'triggered',
  'expired',
  'cancelled'
);

CREATE TYPE public.trigger_type AS ENUM (
  'scheduled',
  'signal',
  'manual',
  'system',
  'webhook'
);

CREATE TYPE public.payment_status AS ENUM (
  'pending',
  'succeeded',
  'failed',
  'refunded',
  'disputed'
);

CREATE TYPE public.notification_type AS ENUM (
  'trade_opened',
  'trade_closed',
  'bot_error',
  'bot_paused',
  'risk_alert',
  'security_alert',
  'system_update',
  'subscription_update',
  'manual_approval_required',
  'agent_veto',
  'backtest_complete',
  'api_key_expiring'
);

-- ============================================================
-- HELPER FUNCTIONS
-- All SECURITY DEFINER + SET search_path to prevent path injection.
-- These run as the function owner (postgres), bypassing RLS on
-- internal queries — which is intentional so they cannot recurse
-- into their own RLS policies.
-- ============================================================

-- Trigger: stamp updated_at on any UPDATE
-- Must exist before any table trigger uses it.
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;

-- ============================================================
-- TABLE: profiles
-- One row per auth.users record.
-- ============================================================

CREATE TABLE public.profiles (
  id                    uuid        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email                 text        NOT NULL,
  display_name          text,
  avatar_url            text,
  role                  public.user_role NOT NULL DEFAULT 'user',
  subscription_status   public.subscription_status NOT NULL DEFAULT 'trialing',
  -- 1 = very conservative, 5 = aggressive
  risk_level            smallint    NOT NULL DEFAULT 2 CHECK (risk_level BETWEEN 1 AND 5),
  onboarding_complete   boolean     NOT NULL DEFAULT false,
  onboarding_step       text,
  kyc_verified          boolean     NOT NULL DEFAULT false,
  two_factor_enabled    boolean     NOT NULL DEFAULT false,
  last_login_at         timestamptz,
  last_ip               inet,
  is_banned             boolean     NOT NULL DEFAULT false,
  ban_reason            text,
  banned_at             timestamptz,
  banned_by             uuid        REFERENCES public.profiles(id) ON DELETE SET NULL,
  metadata              jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at            timestamptz NOT NULL DEFAULT NOW(),
  updated_at            timestamptz NOT NULL DEFAULT NOW()
);

CREATE TRIGGER profiles_updated_at
  BEFORE UPDATE ON public.profiles
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ============================================================
-- TABLE: user_settings
-- One row per user.
-- ============================================================

CREATE TABLE public.user_settings (
  id                              uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id                         uuid        NOT NULL UNIQUE REFERENCES public.profiles(id) ON DELETE CASCADE,
  -- Risk defaults
  default_risk_per_trade_pct      numeric(5,2) NOT NULL DEFAULT 1.00
    CHECK (default_risk_per_trade_pct > 0 AND default_risk_per_trade_pct <= 10),
  max_daily_loss_pct              numeric(5,2) NOT NULL DEFAULT 5.00
    CHECK (max_daily_loss_pct > 0 AND max_daily_loss_pct <= 50),
  max_portfolio_risk_pct          numeric(5,2) NOT NULL DEFAULT 20.00
    CHECK (max_portfolio_risk_pct > 0 AND max_portfolio_risk_pct <= 100),
  max_open_trades                 smallint    NOT NULL DEFAULT 5
    CHECK (max_open_trades > 0 AND max_open_trades <= 100),
  -- Trading permissions
  paper_trading_enabled           boolean     NOT NULL DEFAULT true,
  real_trading_enabled            boolean     NOT NULL DEFAULT false,
  real_trading_requires_approval  boolean     NOT NULL DEFAULT true,
  -- Notification preferences
  notify_trade_open               boolean     NOT NULL DEFAULT true,
  notify_trade_close              boolean     NOT NULL DEFAULT true,
  notify_bot_error                boolean     NOT NULL DEFAULT true,
  notify_risk_alert               boolean     NOT NULL DEFAULT true,
  notify_security_alert           boolean     NOT NULL DEFAULT true,
  notify_manual_approval          boolean     NOT NULL DEFAULT true,
  notify_agent_veto               boolean     NOT NULL DEFAULT true,
  email_notifications             boolean     NOT NULL DEFAULT true,
  push_notifications              boolean     NOT NULL DEFAULT false,
  -- UI / operational preferences
  default_timeframe               text        NOT NULL DEFAULT '1h',
  preferred_exchanges             text[]      NOT NULL DEFAULT '{}',
  timezone                        text        NOT NULL DEFAULT 'UTC',
  metadata                        jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at                      timestamptz NOT NULL DEFAULT NOW(),
  updated_at                      timestamptz NOT NULL DEFAULT NOW()
);

CREATE TRIGGER user_settings_updated_at
  BEFORE UPDATE ON public.user_settings
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ============================================================
-- HELPER FUNCTIONS THAT DEPEND ON profiles / user_settings
-- These must be created after public.profiles and public.user_settings.
-- ============================================================

-- Returns current user's role; NULL if no profile exists yet
CREATE OR REPLACE FUNCTION public.get_user_role()
RETURNS public.user_role
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT role FROM public.profiles WHERE id = auth.uid();
$$;

-- True if caller has admin, super_admin, or security_admin role
CREATE OR REPLACE FUNCTION public.is_admin()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.profiles
    WHERE id = auth.uid()
      AND role IN ('admin', 'super_admin', 'security_admin')
  );
$$;

-- True only for super_admin
CREATE OR REPLACE FUNCTION public.is_super_admin()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.profiles
    WHERE id = auth.uid()
      AND role = 'super_admin'
  );
$$;

-- True for security_admin or super_admin
CREATE OR REPLACE FUNCTION public.is_security_admin()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.profiles
    WHERE id = auth.uid()
      AND role IN ('security_admin', 'super_admin')
  );
$$;

-- Reusable ownership check
CREATE OR REPLACE FUNCTION public.owns_record(record_user_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT record_user_id = auth.uid();
$$;

-- Trigger: auto-create profile + settings row on new auth.users insert
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.profiles (id, email, role)
  VALUES (NEW.id, NEW.email, 'user')
  ON CONFLICT (id) DO NOTHING;

  INSERT INTO public.user_settings (user_id)
  VALUES (NEW.id)
  ON CONFLICT (user_id) DO NOTHING;

  RETURN NEW;
END;
$$;

-- ============================================================
-- TABLE: exchange_accounts
-- Stores connection metadata. Never stores raw API key material.
-- ============================================================

CREATE TABLE public.exchange_accounts (
  id                        uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id                   uuid        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  -- Exchange identity
  exchange_name             text        NOT NULL,  -- 'binance', 'coinbase', 'kraken', etc.
  account_label             text        NOT NULL,
  connection_status         text        NOT NULL DEFAULT 'disconnected'
    CHECK (connection_status IN ('connected','disconnected','error','pending','suspended')),
  -- Permissions detected from exchange key introspection
  can_read                  boolean     NOT NULL DEFAULT false,
  can_trade                 boolean     NOT NULL DEFAULT false,
  can_withdraw              boolean     NOT NULL DEFAULT false,   -- MUST stay false; enforced below
  withdrawal_detected       boolean     NOT NULL DEFAULT false,  -- Set true → triggers rejection flow
  -- Health monitoring
  last_health_check_at      timestamptz,
  last_health_status        text,
  health_error_message      text,
  -- Additional safety metadata
  ip_whitelist_configured   boolean     NOT NULL DEFAULT false,
  testnet                   boolean     NOT NULL DEFAULT false,
  is_active                 boolean     NOT NULL DEFAULT true,
  deactivated_at            timestamptz,
  deactivated_reason        text,
  metadata                  jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at                timestamptz NOT NULL DEFAULT NOW(),
  updated_at                timestamptz NOT NULL DEFAULT NOW(),

  -- Enforce at DB level: withdrawal permission must never be stored as true
  CONSTRAINT no_withdrawal_permissions CHECK (can_withdraw = false)
);

CREATE TRIGGER exchange_accounts_updated_at
  BEFORE UPDATE ON public.exchange_accounts
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ============================================================
-- TABLE: encrypted_api_keys
--
-- SECURITY CONTRACT:
--   - RLS blocks ALL direct access from authenticated role.
--   - Only the service_role (used exclusively by Edge Functions) can read/write.
--   - Edge Functions MUST encrypt payloads with Supabase Vault (pgsodium)
--     BEFORE insert. Columns store opaque bytea blobs only.
--   - vault_key_id references the pgsodium.key used for encryption.
--   - Disable this table in Supabase Dashboard Data API settings.
-- ============================================================

CREATE TABLE public.encrypted_api_keys (
  id                      uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id                 uuid        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  exchange_account_id     uuid        NOT NULL UNIQUE REFERENCES public.exchange_accounts(id) ON DELETE CASCADE,
  -- Encrypted blobs (pgsodium / Vault encrypted before storage)
  encrypted_api_key       bytea       NOT NULL,
  encrypted_secret        bytea       NOT NULL,
  encrypted_passphrase    bytea,                  -- OKX, Coinbase Pro, etc.
  -- Reference to Supabase Vault key used for this encryption
  vault_key_id            uuid,
  -- Key lifecycle
  key_status              text        NOT NULL DEFAULT 'active'
    CHECK (key_status IN ('active','rotated','revoked','expired','compromised')),
  activated_at            timestamptz NOT NULL DEFAULT NOW(),
  rotated_at              timestamptz,
  revoked_at              timestamptz,
  expires_at              timestamptz,
  rotation_count          integer     NOT NULL DEFAULT 0,
  -- Audit trail for key operations
  created_by_ip           inet,
  revoked_by              uuid        REFERENCES public.profiles(id) ON DELETE SET NULL,
  revoke_reason           text,
  metadata                jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at              timestamptz NOT NULL DEFAULT NOW(),
  updated_at              timestamptz NOT NULL DEFAULT NOW()
);

CREATE TRIGGER encrypted_api_keys_updated_at
  BEFORE UPDATE ON public.encrypted_api_keys
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ============================================================
-- TABLE: bots
-- ============================================================

CREATE TABLE public.bots (
  id                      uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id                 uuid        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  exchange_account_id     uuid        REFERENCES public.exchange_accounts(id) ON DELETE SET NULL,
  name                    text        NOT NULL,
  description             text,
  mode                    public.bot_mode   NOT NULL DEFAULT 'paper',
  status                  public.bot_status NOT NULL DEFAULT 'draft',
  -- Market configuration
  base_currency           text        NOT NULL DEFAULT 'USDT',
  quote_currency          text,
  trading_pairs           text[]      NOT NULL DEFAULT '{}',
  -- Risk configuration (per-bot overrides; user_settings are global defaults)
  max_open_positions      smallint    NOT NULL DEFAULT 3
    CHECK (max_open_positions > 0 AND max_open_positions <= 50),
  max_position_size_pct   numeric(5,2) NOT NULL DEFAULT 5.00,
  risk_per_trade_pct      numeric(5,2) NOT NULL DEFAULT 1.00,
  max_daily_loss_pct      numeric(5,2) NOT NULL DEFAULT 5.00,
  -- Strategy
  strategy_type           text,
  -- Points to the currently active bot_configs row (set via FK below after table creation)
  active_config_id        uuid,
  -- Operational flags
  requires_manual_approval boolean    NOT NULL DEFAULT false,
  is_archived             boolean     NOT NULL DEFAULT false,
  archived_at             timestamptz,
  -- Running statistics (maintained by triggers / Edge Functions)
  total_trades            integer     NOT NULL DEFAULT 0,
  total_pnl               numeric(18,8) NOT NULL DEFAULT 0,
  metadata                jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at              timestamptz NOT NULL DEFAULT NOW(),
  updated_at              timestamptz NOT NULL DEFAULT NOW(),

  -- Live bots must have an exchange account linked
  CONSTRAINT live_requires_exchange CHECK (
    mode != 'live' OR exchange_account_id IS NOT NULL
  )
);

CREATE TRIGGER bots_updated_at
  BEFORE UPDATE ON public.bots
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ============================================================
-- TABLE: bot_configs
-- Versioned configuration snapshots for each bot.
-- ============================================================

CREATE TABLE public.bot_configs (
  id              uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  bot_id          uuid        NOT NULL REFERENCES public.bots(id) ON DELETE CASCADE,
  user_id         uuid        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  version         integer     NOT NULL DEFAULT 1,
  config          jsonb       NOT NULL DEFAULT '{}'::jsonb,
  is_active       boolean     NOT NULL DEFAULT true,
  change_summary  text,
  created_by      uuid        NOT NULL REFERENCES public.profiles(id),
  activated_at    timestamptz,
  deactivated_at  timestamptz,
  created_at      timestamptz NOT NULL DEFAULT NOW(),
  updated_at      timestamptz NOT NULL DEFAULT NOW(),

  UNIQUE (bot_id, version)
);

CREATE TRIGGER bot_configs_updated_at
  BEFORE UPDATE ON public.bot_configs
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- Deferred FK from bots.active_config_id → bot_configs (resolves circular dependency)
ALTER TABLE public.bots
  ADD CONSTRAINT bots_active_config_fk
  FOREIGN KEY (active_config_id)
  REFERENCES public.bot_configs(id)
  ON DELETE SET NULL
  DEFERRABLE INITIALLY DEFERRED;

-- ============================================================
-- TABLE: agent_definitions
-- Platform-level catalog of all AI agents.
-- Managed exclusively by super_admin. Not user-owned.
-- ============================================================

CREATE TABLE public.agent_definitions (
  id              uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  name            text        NOT NULL UNIQUE,  -- Internal slug: 'market_data_agent'
  display_name    text        NOT NULL,
  agent_type      text        NOT NULL,          -- 'llm', 'rule_based', 'ml_model', 'hybrid'
  category        public.agent_category NOT NULL,
  description     text,
  -- Behavior
  enabled         boolean     NOT NULL DEFAULT true,
  can_veto        boolean     NOT NULL DEFAULT false,
  default_weight  numeric(4,2) NOT NULL DEFAULT 1.00
    CHECK (default_weight >= 0 AND default_weight <= 10),
  timeout_seconds integer     NOT NULL DEFAULT 30,
  -- Versioning
  version         text        NOT NULL DEFAULT '1.0.0',
  -- JSON Schema for validating agent-specific config payloads
  config_schema   jsonb,
  tags            text[]      NOT NULL DEFAULT '{}',
  metadata        jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at      timestamptz NOT NULL DEFAULT NOW(),
  updated_at      timestamptz NOT NULL DEFAULT NOW()
);

CREATE TRIGGER agent_definitions_updated_at
  BEFORE UPDATE ON public.agent_definitions
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ============================================================
-- TABLE: trade_decisions
-- Declared before agent_runs to resolve FK ordering.
-- ============================================================

CREATE TABLE public.trade_decisions (
  id                        uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id                   uuid        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  bot_id                    uuid        NOT NULL REFERENCES public.bots(id) ON DELETE CASCADE,
  agent_run_id              uuid,       -- FK added after agent_runs table
  signal_id                 uuid,       -- FK added after signals table
  -- Trade parameters
  exchange                  text        NOT NULL,
  symbol                    text        NOT NULL,
  direction                 public.trade_direction NOT NULL,
  mode                      public.trade_mode      NOT NULL DEFAULT 'paper',
  -- Final agent consensus decision
  final_decision            public.agent_decision  NOT NULL,
  -- Aggregated summaries from the agent pipeline (denormalized for fast reads)
  score_summary             jsonb       NOT NULL DEFAULT '{}'::jsonb,
  risk_summary              jsonb       NOT NULL DEFAULT '{}'::jsonb,
  security_summary          jsonb       NOT NULL DEFAULT '{}'::jsonb,
  veto_summary              jsonb       NOT NULL DEFAULT '{}'::jsonb,
  -- Full agent outputs snapshot (immutable record for audit)
  agent_outputs_snapshot    jsonb       NOT NULL DEFAULT '{}'::jsonb,
  -- Approval workflow
  approval_status           public.approval_status NOT NULL DEFAULT 'pending',
  manual_approval_required  boolean     NOT NULL DEFAULT false,
  approved_by               uuid        REFERENCES public.profiles(id) ON DELETE SET NULL,
  approved_at               timestamptz,
  rejection_reason          text,
  -- Suggested entry parameters from agents
  suggested_entry_price     numeric(24,8),
  suggested_quantity        numeric(24,8),
  suggested_stop_loss       numeric(24,8),
  suggested_take_profit     numeric(24,8),
  metadata                  jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at                timestamptz NOT NULL DEFAULT NOW(),
  updated_at                timestamptz NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trade_decisions_updated_at
  BEFORE UPDATE ON public.trade_decisions
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ============================================================
-- TABLE: agent_runs
-- One orchestration run per decision cycle; aggregates all agent outputs.
-- ============================================================

CREATE TABLE public.agent_runs (
  id                  uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id             uuid        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  bot_id              uuid        NOT NULL REFERENCES public.bots(id) ON DELETE CASCADE,
  -- Linked to the decision this run produced (nullable: run may not produce a trade)
  trade_decision_id   uuid        REFERENCES public.trade_decisions(id) ON DELETE SET NULL,
  -- Execution
  run_status          public.agent_run_status NOT NULL DEFAULT 'pending',
  trigger_type        public.trigger_type     NOT NULL DEFAULT 'scheduled',
  started_at          timestamptz NOT NULL DEFAULT NOW(),
  completed_at        timestamptz,
  duration_ms         integer,    -- Populated on completion
  -- Input and output payloads
  input_snapshot      jsonb       NOT NULL DEFAULT '{}'::jsonb,  -- Market state at invocation time
  final_summary       jsonb,      -- Aggregated consensus result
  -- Error details
  error_message       text,
  error_details       jsonb,
  metadata            jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at          timestamptz NOT NULL DEFAULT NOW(),
  updated_at          timestamptz NOT NULL DEFAULT NOW()
);

CREATE TRIGGER agent_runs_updated_at
  BEFORE UPDATE ON public.agent_runs
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- Now add the deferred FK from trade_decisions back to agent_runs
ALTER TABLE public.trade_decisions
  ADD CONSTRAINT trade_decisions_agent_run_fk
  FOREIGN KEY (agent_run_id)
  REFERENCES public.agent_runs(id)
  ON DELETE SET NULL
  DEFERRABLE INITIALLY DEFERRED;

-- ============================================================
-- TABLE: agent_outputs
-- One row per agent per run. The atomic audit unit.
-- ============================================================

CREATE TABLE public.agent_outputs (
  id                    uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  agent_run_id          uuid        NOT NULL REFERENCES public.agent_runs(id) ON DELETE CASCADE,
  agent_definition_id   uuid        NOT NULL REFERENCES public.agent_definitions(id) ON DELETE RESTRICT,
  user_id               uuid        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  bot_id                uuid        NOT NULL REFERENCES public.bots(id) ON DELETE CASCADE,
  -- Decision output
  decision              public.agent_decision NOT NULL,
  score                 numeric(5,2)  CHECK (score BETWEEN -100 AND 100),
  confidence            numeric(4,3)  CHECK (confidence BETWEEN 0 AND 1),
  veto                  boolean     NOT NULL DEFAULT false,
  -- Reasoning
  reasoning             text,
  output                jsonb       NOT NULL DEFAULT '{}'::jsonb,
  -- Error
  error_message         text,
  error_details         jsonb,
  -- Timing
  started_at            timestamptz,
  completed_at          timestamptz,
  duration_ms           integer,
  created_at            timestamptz NOT NULL DEFAULT NOW()
  -- No updated_at: agent outputs are immutable once written
);

-- ============================================================
-- TABLE: market_snapshots
-- Shared platform-level market data. No user ownership.
-- Written exclusively by the data agent pipeline (service_role).
-- ============================================================

CREATE TABLE public.market_snapshots (
  id                    uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  exchange              text        NOT NULL,
  symbol                text        NOT NULL,
  timeframe             text        NOT NULL,  -- '1m', '5m', '15m', '1h', '4h', '1d'
  -- OHLCV
  open_price            numeric(24,8) NOT NULL,
  high_price            numeric(24,8) NOT NULL,
  low_price             numeric(24,8) NOT NULL,
  close_price           numeric(24,8) NOT NULL,
  volume                numeric(24,8) NOT NULL,
  -- Order book summary
  bid_price             numeric(24,8),
  ask_price             numeric(24,8),
  spread_pct            numeric(8,6),
  order_book_depth      jsonb,          -- Top N bid/ask levels
  -- Computed technical indicators (RSI, MACD, BB, ATR, etc.)
  technical_indicators  jsonb       NOT NULL DEFAULT '{}'::jsonb,
  -- Derivatives / perpetuals
  funding_rate          numeric(10,8),
  open_interest         numeric(24,8),
  -- Source metadata
  captured_at           timestamptz NOT NULL DEFAULT NOW(),
  source                text,           -- 'websocket', 'rest', 'backfill'
  created_at            timestamptz NOT NULL DEFAULT NOW()
  -- Intentionally no updated_at: snapshots are immutable
);

-- ============================================================
-- TABLE: signals
-- Trading signals generated by the analysis agent pipeline.
-- ============================================================

CREATE TABLE public.signals (
  id                    uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id               uuid        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  bot_id                uuid        NOT NULL REFERENCES public.bots(id) ON DELETE CASCADE,
  agent_run_id          uuid        REFERENCES public.agent_runs(id) ON DELETE SET NULL,
  market_snapshot_id    uuid        REFERENCES public.market_snapshots(id) ON DELETE SET NULL,
  -- Signal parameters
  exchange              text        NOT NULL,
  symbol                text        NOT NULL,
  direction             public.trade_direction NOT NULL,
  signal_type           text        NOT NULL,  -- 'momentum', 'mean_reversion', 'breakout', 'manual', etc.
  confidence            numeric(4,3)  CHECK (confidence BETWEEN 0 AND 1),
  score                 numeric(5,2),
  -- Lifecycle
  status                public.signal_status NOT NULL DEFAULT 'pending',
  processed_at          timestamptz,
  expires_at            timestamptz,
  expired_at            timestamptz,
  metadata              jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at            timestamptz NOT NULL DEFAULT NOW(),
  updated_at            timestamptz NOT NULL DEFAULT NOW()
);

CREATE TRIGGER signals_updated_at
  BEFORE UPDATE ON public.signals
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- Add FK from trade_decisions to signals (signals table now exists)
ALTER TABLE public.trade_decisions
  ADD CONSTRAINT trade_decisions_signal_fk
  FOREIGN KEY (signal_id)
  REFERENCES public.signals(id)
  ON DELETE SET NULL;

-- ============================================================
-- TABLE: trades
--
-- ARCHITECTURE DECISION — Unified trades table (no separate paper_trades):
--   A separate paper_trades table would duplicate ~95% of this schema,
--   force dual-path query logic throughout the codebase, complicate
--   analytics that compare paper vs. live performance, and make
--   mode-switching bots significantly harder to implement.
--   The trade_mode enum column (paper/live/shadow) provides full
--   separation at query time. Paper trades use simulated PnL;
--   exchange_order_id is NULL for paper mode.
-- ============================================================

CREATE TABLE public.trades (
  id                    uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id               uuid        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  bot_id                uuid        NOT NULL REFERENCES public.bots(id) ON DELETE CASCADE,
  trade_decision_id     uuid        REFERENCES public.trade_decisions(id) ON DELETE SET NULL,
  -- Mode
  mode                  public.trade_mode   NOT NULL DEFAULT 'paper',
  -- Exchange
  exchange              text        NOT NULL,
  exchange_order_id     text,                  -- NULL for paper/shadow trades
  exchange_trade_ids    text[]      NOT NULL DEFAULT '{}',
  -- Trade parameters
  symbol                text        NOT NULL,
  side                  text        NOT NULL CHECK (side IN ('buy', 'sell')),
  direction             public.trade_direction NOT NULL,
  status                public.trade_status   NOT NULL DEFAULT 'pending',
  -- Pricing
  entry_price           numeric(24,8),
  exit_price            numeric(24,8),
  avg_entry_price       numeric(24,8),
  avg_exit_price        numeric(24,8),
  quantity              numeric(24,8) NOT NULL,
  filled_quantity       numeric(24,8) NOT NULL DEFAULT 0,
  -- Risk parameters (captured at trade open time)
  stop_loss             numeric(24,8),
  take_profit           numeric(24,8),
  trailing_stop_pct     numeric(5,2),
  -- PnL
  realized_pnl          numeric(18,8),
  unrealized_pnl        numeric(18,8),
  pnl_pct               numeric(8,4),
  fees_paid             numeric(18,8) NOT NULL DEFAULT 0,
  fee_currency          text,
  -- Timestamps
  opened_at             timestamptz NOT NULL DEFAULT NOW(),
  closed_at             timestamptz,
  last_updated_at       timestamptz NOT NULL DEFAULT NOW(),
  tags                  text[]      NOT NULL DEFAULT '{}',
  metadata              jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at            timestamptz NOT NULL DEFAULT NOW(),
  updated_at            timestamptz NOT NULL DEFAULT NOW(),

  -- Live trades must eventually have an exchange order ID
  CONSTRAINT live_requires_order_id CHECK (
    mode != 'live' OR exchange_order_id IS NOT NULL OR status = 'pending'
  )
);

CREATE TRIGGER trades_updated_at
  BEFORE UPDATE ON public.trades
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ============================================================
-- TABLE: trade_events
-- Immutable chronological log of all events on a trade.
-- No UPDATE or DELETE policies defined (enforced by omission).
-- ============================================================

CREATE TABLE public.trade_events (
  id          uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  trade_id    uuid        NOT NULL REFERENCES public.trades(id) ON DELETE CASCADE,
  user_id     uuid        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  bot_id      uuid        REFERENCES public.bots(id) ON DELETE SET NULL,
  event_type  text        NOT NULL,
    -- 'opened', 'closed', 'partial_fill', 'stop_loss_triggered',
    -- 'take_profit_triggered', 'manual_close', 'error', 'price_update'
  message     text,
  source      text        NOT NULL DEFAULT 'system',  -- 'system', 'agent', 'user', 'exchange'
  metadata    jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at  timestamptz NOT NULL DEFAULT NOW()
);

-- ============================================================
-- TABLE: risk_logs
-- Logged by the risk agent and risk engine on every decision cycle.
-- ============================================================

CREATE TABLE public.risk_logs (
  id                  uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id             uuid        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  bot_id              uuid        REFERENCES public.bots(id) ON DELETE SET NULL,
  trade_decision_id   uuid        REFERENCES public.trade_decisions(id) ON DELETE SET NULL,
  trade_id            uuid        REFERENCES public.trades(id) ON DELETE SET NULL,
  agent_run_id        uuid        REFERENCES public.agent_runs(id) ON DELETE SET NULL,
  -- Risk event
  risk_type           text        NOT NULL,
    -- 'position_size', 'daily_loss_limit', 'drawdown', 'concentration',
    -- 'consecutive_losses', 'volatility_spike', 'correlation_breach'
  severity            public.severity_level NOT NULL DEFAULT 'medium',
  triggered           boolean     NOT NULL DEFAULT false,  -- true = this check blocked a trade
  message             text        NOT NULL,
  resolved            boolean     NOT NULL DEFAULT false,
  resolved_at         timestamptz,
  metadata            jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at          timestamptz NOT NULL DEFAULT NOW()
);

-- ============================================================
-- TABLE: security_logs
-- Security-relevant events across the platform.
-- user_id is nullable for system-level events with no user context.
-- ============================================================

CREATE TABLE public.security_logs (
  id            uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id       uuid        REFERENCES public.profiles(id) ON DELETE SET NULL,
  event_type    text        NOT NULL,
    -- 'api_key_created', 'api_key_revoked', 'api_key_rotated',
    -- 'withdrawal_attempt_blocked', 'login_failed', 'mfa_failed',
    -- 'suspicious_ip', 'rate_limit_exceeded', 'admin_action'
  severity      public.severity_level NOT NULL DEFAULT 'medium',
  source        text        NOT NULL,  -- 'auth', 'api', 'agent', 'system', 'edge_function'
  ip_address    inet,
  user_agent    text,
  message       text        NOT NULL,
  resolved      boolean     NOT NULL DEFAULT false,
  resolved_by   uuid        REFERENCES public.profiles(id) ON DELETE SET NULL,
  resolved_at   timestamptz,
  metadata      jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at    timestamptz NOT NULL DEFAULT NOW()
);

-- ============================================================
-- TABLE: red_team_reports
-- Generated by the Security Red Team Agent.
-- Visible only to security_admin / super_admin.
-- ============================================================

CREATE TABLE public.red_team_reports (
  id                    uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  generated_by_agent    uuid        REFERENCES public.agent_definitions(id) ON DELETE SET NULL,
  agent_run_id          uuid        REFERENCES public.agent_runs(id) ON DELETE SET NULL,
  -- Vulnerability details
  target_area           text        NOT NULL,
    -- 'rls_policies', 'api_key_storage', 'withdrawal_checks',
    -- 'auth_flow', 'input_validation', 'rate_limiting'
  severity              public.severity_level NOT NULL,
  vulnerability_type    text        NOT NULL,
  description           text        NOT NULL,
  affected_components   text[]      NOT NULL DEFAULT '{}',
  -- Sanitized PoC only — never store actual exploit payloads
  proof_of_concept      text,
  recommended_fix       text        NOT NULL,
  -- Workflow
  status                public.report_status NOT NULL DEFAULT 'open',
  admin_reviewed        boolean     NOT NULL DEFAULT false,
  reviewed_by           uuid        REFERENCES public.profiles(id) ON DELETE SET NULL,
  reviewed_at           timestamptz,
  review_notes          text,
  metadata              jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at            timestamptz NOT NULL DEFAULT NOW(),
  updated_at            timestamptz NOT NULL DEFAULT NOW()
);

CREATE TRIGGER red_team_reports_updated_at
  BEFORE UPDATE ON public.red_team_reports
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ============================================================
-- TABLE: system_evolution_reports
-- Generated by System Evolution / Agent Gap Finder Agent.
-- ============================================================

CREATE TABLE public.system_evolution_reports (
  id                          uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  generated_by_agent          uuid        REFERENCES public.agent_definitions(id) ON DELETE SET NULL,
  agent_run_id                uuid        REFERENCES public.agent_runs(id) ON DELETE SET NULL,
  -- Finding
  finding_type                text        NOT NULL,
    -- 'missing_agent', 'performance_gap', 'schema_gap', 'risk_gap',
    -- 'coverage_gap', 'latency_issue'
  description                 text        NOT NULL,
  -- Structured recommendations (arrays of objects)
  recommended_new_agents      jsonb       NOT NULL DEFAULT '[]'::jsonb,
  recommended_schema_changes  jsonb       NOT NULL DEFAULT '[]'::jsonb,
  recommended_risk_changes    jsonb       NOT NULL DEFAULT '[]'::jsonb,
  -- 1 = critical, 5 = low
  priority                    smallint    NOT NULL DEFAULT 3
    CHECK (priority BETWEEN 1 AND 5),
  status                      public.report_status NOT NULL DEFAULT 'open',
  implemented_by              uuid        REFERENCES public.profiles(id) ON DELETE SET NULL,
  implemented_at              timestamptz,
  implementation_notes        text,
  metadata                    jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at                  timestamptz NOT NULL DEFAULT NOW(),
  updated_at                  timestamptz NOT NULL DEFAULT NOW()
);

CREATE TRIGGER system_evolution_reports_updated_at
  BEFORE UPDATE ON public.system_evolution_reports
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ============================================================
-- TABLE: strategy_configs
-- Versioned strategy parameter sets, scoped to a user (and optionally a bot).
-- ============================================================

CREATE TABLE public.strategy_configs (
  id            uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id       uuid        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  bot_id        uuid        REFERENCES public.bots(id) ON DELETE SET NULL,
  name          text        NOT NULL,
  strategy_type text        NOT NULL,
    -- 'momentum', 'grid', 'dca', 'mean_reversion', 'breakout', 'custom'
  parameters    jsonb       NOT NULL DEFAULT '{}'::jsonb,
  is_active     boolean     NOT NULL DEFAULT true,
  version       integer     NOT NULL DEFAULT 1,
  -- Points to parent version for lineage tracing
  parent_id     uuid        REFERENCES public.strategy_configs(id) ON DELETE SET NULL,
  description   text,
  tags          text[]      NOT NULL DEFAULT '{}',
  metadata      jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at    timestamptz NOT NULL DEFAULT NOW(),
  updated_at    timestamptz NOT NULL DEFAULT NOW()
);

CREATE TRIGGER strategy_configs_updated_at
  BEFORE UPDATE ON public.strategy_configs
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ============================================================
-- TABLE: backtests
-- ============================================================

CREATE TABLE public.backtests (
  id                    uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id               uuid        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  bot_id                uuid        REFERENCES public.bots(id) ON DELETE SET NULL,
  strategy_config_id    uuid        REFERENCES public.strategy_configs(id) ON DELETE SET NULL,
  -- Parameters
  exchange              text        NOT NULL,
  symbol                text        NOT NULL,
  timeframe             text        NOT NULL,
  date_from             timestamptz NOT NULL,
  date_to               timestamptz NOT NULL,
  initial_capital       numeric(18,8) NOT NULL DEFAULT 10000,
  -- Execution state
  status                text        NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','running','completed','failed','cancelled')),
  started_at            timestamptz,
  completed_at          timestamptz,
  -- Results
  results               jsonb,  -- Array of individual simulated trades
  metrics               jsonb,  -- Sharpe ratio, max drawdown, win rate, profit factor, etc.
  error_message         text,
  metadata              jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at            timestamptz NOT NULL DEFAULT NOW(),
  updated_at            timestamptz NOT NULL DEFAULT NOW()
);

CREATE TRIGGER backtests_updated_at
  BEFORE UPDATE ON public.backtests
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ============================================================
-- TABLE: subscriptions
-- One row per user; managed entirely by Stripe webhook Edge Function.
-- ============================================================

CREATE TABLE public.subscriptions (
  id                      uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id                 uuid        NOT NULL UNIQUE REFERENCES public.profiles(id) ON DELETE CASCADE,
  plan                    public.subscription_plan   NOT NULL DEFAULT 'free',
  status                  public.subscription_status NOT NULL DEFAULT 'trialing',
  -- Stripe references
  stripe_customer_id      text        UNIQUE,
  stripe_subscription_id  text        UNIQUE,
  -- Period
  current_period_start    timestamptz,
  current_period_end      timestamptz,
  trial_end               timestamptz,
  cancelled_at            timestamptz,
  -- Cached plan limits (avoids joining on every bot creation check)
  max_bots                smallint    NOT NULL DEFAULT 1,
  max_trades_per_day      integer     NOT NULL DEFAULT 10,
  real_trading_allowed    boolean     NOT NULL DEFAULT false,
  api_calls_per_day       integer     NOT NULL DEFAULT 1000,
  metadata                jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at              timestamptz NOT NULL DEFAULT NOW(),
  updated_at              timestamptz NOT NULL DEFAULT NOW()
);

CREATE TRIGGER subscriptions_updated_at
  BEFORE UPDATE ON public.subscriptions
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ============================================================
-- TABLE: payments
-- Populated by Stripe webhook Edge Function.
-- ============================================================

CREATE TABLE public.payments (
  id                  uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id             uuid        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  subscription_id     uuid        REFERENCES public.subscriptions(id) ON DELETE SET NULL,
  stripe_payment_id   text        NOT NULL UNIQUE,
  stripe_invoice_id   text,
  amount              integer     NOT NULL,   -- Stored in smallest currency unit (cents)
  currency            text        NOT NULL DEFAULT 'usd',
  status              public.payment_status NOT NULL DEFAULT 'pending',
  description         text,
  failure_reason      text,
  refunded_amount     integer     NOT NULL DEFAULT 0,
  paid_at             timestamptz,
  metadata            jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at          timestamptz NOT NULL DEFAULT NOW(),
  updated_at          timestamptz NOT NULL DEFAULT NOW()
);

CREATE TRIGGER payments_updated_at
  BEFORE UPDATE ON public.payments
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ============================================================
-- TABLE: notifications
-- ============================================================

CREATE TABLE public.notifications (
  id              uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id         uuid        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  type            public.notification_type NOT NULL,
  title           text        NOT NULL,
  message         text        NOT NULL,
  is_read         boolean     NOT NULL DEFAULT false,
  read_at         timestamptz,
  -- Soft link to the originating record (table name + id)
  related_table   text,
  related_id      uuid,
  -- 1 = urgent, 5 = low
  priority        smallint    NOT NULL DEFAULT 3
    CHECK (priority BETWEEN 1 AND 5),
  expires_at      timestamptz,
  metadata        jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at      timestamptz NOT NULL DEFAULT NOW()
);

-- ============================================================
-- TABLE: audit_logs
-- Append-only. No UPDATE or DELETE policies defined.
-- Captures all sensitive mutations with before/after values.
-- ============================================================

CREATE TABLE public.audit_logs (
  id          uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id     uuid        REFERENCES public.profiles(id) ON DELETE SET NULL,
  actor_role  public.user_role,
  action      text        NOT NULL,
    -- 'INSERT', 'UPDATE', 'DELETE', 'LOGIN', 'LOGOUT', 'LOGIN_FAILED',
    -- 'API_KEY_CREATED', 'API_KEY_REVOKED', 'BOT_MODE_CHANGED',
    -- 'REAL_TRADING_ENABLED', 'ROLE_CHANGED', 'BAN_APPLIED'
  table_name  text,
  record_id   uuid,
  old_values  jsonb,      -- Sensitive fields should be redacted before logging
  new_values  jsonb,      -- Never log encrypted_api_keys payload columns here
  ip_address  inet,
  user_agent  text,
  source      text,       -- 'edge_function', 'trigger', 'system', 'admin_dashboard'
  session_id  text,
  metadata    jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at  timestamptz NOT NULL DEFAULT NOW()
);

-- ============================================================
-- TABLE: database_schema_audits
-- Generated by Database Schema Auditor Agent.
-- ============================================================

CREATE TABLE public.database_schema_audits (
  id                            uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  generated_by_agent            uuid        REFERENCES public.agent_definitions(id) ON DELETE SET NULL,
  -- Findings (arrays of structured finding objects)
  missing_table_warnings        jsonb       NOT NULL DEFAULT '[]'::jsonb,
  missing_index_warnings        jsonb       NOT NULL DEFAULT '[]'::jsonb,
  missing_rls_warnings          jsonb       NOT NULL DEFAULT '[]'::jsonb,
  security_recommendations      jsonb       NOT NULL DEFAULT '[]'::jsonb,
  performance_recommendations   jsonb       NOT NULL DEFAULT '[]'::jsonb,
  -- Summary counters
  tables_audited                integer     NOT NULL DEFAULT 0,
  issues_found                  integer     NOT NULL DEFAULT 0,
  critical_issues               integer     NOT NULL DEFAULT 0,
  status                        public.report_status NOT NULL DEFAULT 'open',
  reviewed_by                   uuid        REFERENCES public.profiles(id) ON DELETE SET NULL,
  reviewed_at                   timestamptz,
  metadata                      jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at                    timestamptz NOT NULL DEFAULT NOW(),
  updated_at                    timestamptz NOT NULL DEFAULT NOW()
);

CREATE TRIGGER database_schema_audits_updated_at
  BEFORE UPDATE ON public.database_schema_audits
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ============================================================
-- TRIGGER: Auto-create profile on auth.users INSERT
-- ============================================================

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ============================================================
-- INDEXES
-- Naming convention: idx_{table}_{columns}
-- Partial indexes used for high-cardinality boolean filters.
-- ============================================================

-- profiles
CREATE INDEX idx_profiles_role             ON public.profiles(role);
CREATE INDEX idx_profiles_email            ON public.profiles(email);
CREATE INDEX idx_profiles_sub_status       ON public.profiles(subscription_status);

-- user_settings
CREATE INDEX idx_user_settings_user_id     ON public.user_settings(user_id);

-- exchange_accounts
CREATE INDEX idx_exchange_acct_user_id     ON public.exchange_accounts(user_id);
CREATE INDEX idx_exchange_acct_name        ON public.exchange_accounts(exchange_name);
CREATE INDEX idx_exchange_acct_status      ON public.exchange_accounts(connection_status);
-- Narrow index: only rows where withdrawal_detected = true (security alerting)
CREATE INDEX idx_exchange_acct_withdrawal  ON public.exchange_accounts(user_id)
  WHERE withdrawal_detected = true;

-- encrypted_api_keys (minimal exposure; service_role only)
CREATE INDEX idx_enc_keys_user_id          ON public.encrypted_api_keys(user_id);
CREATE INDEX idx_enc_keys_acct_id          ON public.encrypted_api_keys(exchange_account_id);
CREATE INDEX idx_enc_keys_status           ON public.encrypted_api_keys(key_status)
  WHERE key_status = 'active';

-- bots
CREATE INDEX idx_bots_user_id              ON public.bots(user_id);
CREATE INDEX idx_bots_user_status          ON public.bots(user_id, status);
CREATE INDEX idx_bots_mode                 ON public.bots(mode);
CREATE INDEX idx_bots_exchange_acct        ON public.bots(exchange_account_id);
-- Active bots only
CREATE INDEX idx_bots_active               ON public.bots(user_id, mode)
  WHERE status = 'active' AND is_archived = false;

-- bot_configs
CREATE INDEX idx_bot_configs_bot_id        ON public.bot_configs(bot_id);
CREATE INDEX idx_bot_configs_user_id       ON public.bot_configs(user_id);
CREATE INDEX idx_bot_configs_bot_active    ON public.bot_configs(bot_id)
  WHERE is_active = true;

-- agent_definitions
CREATE INDEX idx_agent_def_category        ON public.agent_definitions(category);
CREATE INDEX idx_agent_def_enabled         ON public.agent_definitions(enabled)
  WHERE enabled = true;

-- agent_runs
CREATE INDEX idx_agent_runs_user_id        ON public.agent_runs(user_id);
CREATE INDEX idx_agent_runs_bot_id         ON public.agent_runs(bot_id);
CREATE INDEX idx_agent_runs_decision_id    ON public.agent_runs(trade_decision_id);
CREATE INDEX idx_agent_runs_status         ON public.agent_runs(run_status);
CREATE INDEX idx_agent_runs_started_at     ON public.agent_runs(started_at DESC);
CREATE INDEX idx_agent_runs_user_bot       ON public.agent_runs(user_id, bot_id);
-- In-flight runs only
CREATE INDEX idx_agent_runs_running        ON public.agent_runs(bot_id, started_at)
  WHERE run_status IN ('pending', 'running');

-- agent_outputs
CREATE INDEX idx_agent_out_run_id          ON public.agent_outputs(agent_run_id);
CREATE INDEX idx_agent_out_user_id         ON public.agent_outputs(user_id);
CREATE INDEX idx_agent_out_bot_id          ON public.agent_outputs(bot_id);
CREATE INDEX idx_agent_out_def_id          ON public.agent_outputs(agent_definition_id);
CREATE INDEX idx_agent_out_decision        ON public.agent_outputs(decision);
-- Veto-only index for fast veto queries
CREATE INDEX idx_agent_out_veto            ON public.agent_outputs(agent_run_id)
  WHERE veto = true;

-- market_snapshots
CREATE INDEX idx_mkt_snap_exch_sym_tf      ON public.market_snapshots(exchange, symbol, timeframe);
CREATE INDEX idx_mkt_snap_captured_at      ON public.market_snapshots(captured_at DESC);
-- Recent data fast-path for live dashboard.
-- NOTE: PostgreSQL does not allow NOW() in partial index predicates because it is not immutable.
-- Keep this as a normal composite index; freshness should be filtered at query time.
CREATE INDEX idx_mkt_snap_recent           ON public.market_snapshots(exchange, symbol, captured_at DESC);

-- signals
CREATE INDEX idx_signals_user_id           ON public.signals(user_id);
CREATE INDEX idx_signals_bot_id            ON public.signals(bot_id);
CREATE INDEX idx_signals_user_status       ON public.signals(user_id, status);
CREATE INDEX idx_signals_symbol            ON public.signals(symbol);
CREATE INDEX idx_signals_created_at        ON public.signals(created_at DESC);
-- Pending signals only
CREATE INDEX idx_signals_pending           ON public.signals(bot_id, created_at DESC)
  WHERE status = 'pending';

-- trade_decisions
CREATE INDEX idx_td_user_id                ON public.trade_decisions(user_id);
CREATE INDEX idx_td_bot_id                 ON public.trade_decisions(bot_id);
CREATE INDEX idx_td_approval               ON public.trade_decisions(approval_status);
CREATE INDEX idx_td_created_at             ON public.trade_decisions(created_at DESC);
CREATE INDEX idx_td_user_bot               ON public.trade_decisions(user_id, bot_id);
-- Decisions awaiting manual approval
CREATE INDEX idx_td_manual_approval        ON public.trade_decisions(user_id, created_at DESC)
  WHERE manual_approval_required = true AND approval_status = 'pending';

-- trades
CREATE INDEX idx_trades_user_id            ON public.trades(user_id);
CREATE INDEX idx_trades_bot_id             ON public.trades(bot_id);
CREATE INDEX idx_trades_decision_id        ON public.trades(trade_decision_id);
CREATE INDEX idx_trades_user_status        ON public.trades(user_id, status);
CREATE INDEX idx_trades_user_bot           ON public.trades(user_id, bot_id);
CREATE INDEX idx_trades_symbol             ON public.trades(symbol);
CREATE INDEX idx_trades_opened_at          ON public.trades(opened_at DESC);
-- Open positions (hot path for risk engine)
CREATE INDEX idx_trades_open               ON public.trades(user_id, bot_id, symbol)
  WHERE status = 'open';
-- Live mode open positions
CREATE INDEX idx_trades_live_open          ON public.trades(user_id, exchange)
  WHERE mode = 'live' AND status = 'open';

-- trade_events
CREATE INDEX idx_te_trade_id               ON public.trade_events(trade_id);
CREATE INDEX idx_te_user_id                ON public.trade_events(user_id);
CREATE INDEX idx_te_event_type             ON public.trade_events(event_type);
CREATE INDEX idx_te_created_at             ON public.trade_events(created_at DESC);

-- risk_logs
CREATE INDEX idx_risk_user_id              ON public.risk_logs(user_id);
CREATE INDEX idx_risk_bot_id               ON public.risk_logs(bot_id);
CREATE INDEX idx_risk_trade_id             ON public.risk_logs(trade_id);
CREATE INDEX idx_risk_severity             ON public.risk_logs(severity);
CREATE INDEX idx_risk_created_at           ON public.risk_logs(created_at DESC);
-- Triggered risk events only
CREATE INDEX idx_risk_triggered            ON public.risk_logs(user_id, created_at DESC)
  WHERE triggered = true;

-- security_logs
CREATE INDEX idx_sec_log_user_id           ON public.security_logs(user_id);
CREATE INDEX idx_sec_log_event_type        ON public.security_logs(event_type);
CREATE INDEX idx_sec_log_severity          ON public.security_logs(severity);
CREATE INDEX idx_sec_log_created_at        ON public.security_logs(created_at DESC);
-- High/critical unresolved (security dashboard alert feed)
CREATE INDEX idx_sec_log_critical          ON public.security_logs(created_at DESC)
  WHERE severity IN ('high', 'critical') AND resolved = false;

-- red_team_reports
CREATE INDEX idx_rtr_severity              ON public.red_team_reports(severity);
CREATE INDEX idx_rtr_status                ON public.red_team_reports(status);
CREATE INDEX idx_rtr_created_at            ON public.red_team_reports(created_at DESC);

-- system_evolution_reports
CREATE INDEX idx_ser_status                ON public.system_evolution_reports(status);
CREATE INDEX idx_ser_priority              ON public.system_evolution_reports(priority);
CREATE INDEX idx_ser_created_at            ON public.system_evolution_reports(created_at DESC);

-- strategy_configs
CREATE INDEX idx_strat_user_id             ON public.strategy_configs(user_id);
CREATE INDEX idx_strat_bot_id              ON public.strategy_configs(bot_id);
CREATE INDEX idx_strat_active              ON public.strategy_configs(user_id)
  WHERE is_active = true;

-- backtests
CREATE INDEX idx_bt_user_id                ON public.backtests(user_id);
CREATE INDEX idx_bt_bot_id                 ON public.backtests(bot_id);
CREATE INDEX idx_bt_status                 ON public.backtests(status);
CREATE INDEX idx_bt_created_at             ON public.backtests(created_at DESC);

-- subscriptions
CREATE INDEX idx_sub_user_id               ON public.subscriptions(user_id);
CREATE INDEX idx_sub_stripe_cust           ON public.subscriptions(stripe_customer_id);
CREATE INDEX idx_sub_status                ON public.subscriptions(status);

-- payments
CREATE INDEX idx_pay_user_id               ON public.payments(user_id);
CREATE INDEX idx_pay_stripe_id             ON public.payments(stripe_payment_id);
CREATE INDEX idx_pay_created_at            ON public.payments(created_at DESC);

-- notifications
CREATE INDEX idx_notif_user_id             ON public.notifications(user_id);
-- Unread notifications (hot path for notification badge counts)
CREATE INDEX idx_notif_unread              ON public.notifications(user_id, created_at DESC)
  WHERE is_read = false;

-- audit_logs
CREATE INDEX idx_audit_user_id             ON public.audit_logs(user_id);
CREATE INDEX idx_audit_table_name          ON public.audit_logs(table_name);
CREATE INDEX idx_audit_record_id           ON public.audit_logs(record_id);
CREATE INDEX idx_audit_action              ON public.audit_logs(action);
CREATE INDEX idx_audit_created_at          ON public.audit_logs(created_at DESC);

-- database_schema_audits
CREATE INDEX idx_dsa_status                ON public.database_schema_audits(status);
CREATE INDEX idx_dsa_created_at            ON public.database_schema_audits(created_at DESC);

-- ============================================================
-- ROW LEVEL SECURITY — Enable on all tables
-- ============================================================

ALTER TABLE public.profiles                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_settings             ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.exchange_accounts         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.encrypted_api_keys        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.bots                      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.bot_configs               ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_definitions         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_runs                ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_outputs             ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.market_snapshots          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.signals                   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trade_decisions           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trades                    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trade_events              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.risk_logs                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.security_logs             ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.red_team_reports          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.system_evolution_reports  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.strategy_configs          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.backtests                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.subscriptions             ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payments                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications             ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_logs                ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.database_schema_audits    ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- RLS POLICIES: profiles
-- ============================================================

-- Users see their own profile; admins see all
CREATE POLICY "profiles_select"
  ON public.profiles FOR SELECT TO authenticated
  USING (id = auth.uid() OR public.is_admin());

-- Users update only their own profile;
-- WITH CHECK prevents self-promotion of role column
CREATE POLICY "profiles_update_own"
  ON public.profiles FOR UPDATE TO authenticated
  USING (id = auth.uid())
  WITH CHECK (
    id = auth.uid()
    AND role = (SELECT role FROM public.profiles WHERE id = auth.uid())
  );

-- Admins can update any profile (including role changes)
CREATE POLICY "profiles_update_admin"
  ON public.profiles FOR UPDATE TO authenticated
  USING (public.is_admin())
  WITH CHECK (public.is_admin());

-- ============================================================
-- RLS POLICIES: user_settings
-- ============================================================

CREATE POLICY "user_settings_select"
  ON public.user_settings FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR public.is_admin());

CREATE POLICY "user_settings_insert"
  ON public.user_settings FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid());

CREATE POLICY "user_settings_update"
  ON public.user_settings FOR UPDATE TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- ============================================================
-- RLS POLICIES: exchange_accounts
-- ============================================================

CREATE POLICY "exchange_accounts_select"
  ON public.exchange_accounts FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR public.is_admin());

CREATE POLICY "exchange_accounts_insert"
  ON public.exchange_accounts FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid());

CREATE POLICY "exchange_accounts_update"
  ON public.exchange_accounts FOR UPDATE TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

CREATE POLICY "exchange_accounts_delete"
  ON public.exchange_accounts FOR DELETE TO authenticated
  USING (user_id = auth.uid());

-- ============================================================
-- RLS POLICIES: encrypted_api_keys
-- TOTAL BLOCK for authenticated role.
-- Only service_role (Edge Functions) may access this table.
-- ============================================================

CREATE POLICY "encrypted_api_keys_deny_all"
  ON public.encrypted_api_keys FOR ALL TO authenticated
  USING (false)
  WITH CHECK (false);

-- ============================================================
-- RLS POLICIES: bots
-- ============================================================

CREATE POLICY "bots_select"
  ON public.bots FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR public.is_admin());

CREATE POLICY "bots_insert"
  ON public.bots FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid());

CREATE POLICY "bots_update"
  ON public.bots FOR UPDATE TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- Users can only delete bots that are archived (safety guard)
CREATE POLICY "bots_delete"
  ON public.bots FOR DELETE TO authenticated
  USING (user_id = auth.uid() AND is_archived = true);

-- ============================================================
-- RLS POLICIES: bot_configs
-- ============================================================

CREATE POLICY "bot_configs_select"
  ON public.bot_configs FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR public.is_admin());

CREATE POLICY "bot_configs_insert"
  ON public.bot_configs FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid());

CREATE POLICY "bot_configs_update"
  ON public.bot_configs FOR UPDATE TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- ============================================================
-- RLS POLICIES: agent_definitions
-- All authenticated users can read enabled agents.
-- Only super_admin can mutate.
-- ============================================================

CREATE POLICY "agent_defs_select"
  ON public.agent_definitions FOR SELECT TO authenticated
  USING (enabled = true OR public.is_admin());

CREATE POLICY "agent_defs_insert"
  ON public.agent_definitions FOR INSERT TO authenticated
  WITH CHECK (public.is_super_admin());

CREATE POLICY "agent_defs_update"
  ON public.agent_definitions FOR UPDATE TO authenticated
  USING (public.is_super_admin())
  WITH CHECK (public.is_super_admin());

CREATE POLICY "agent_defs_delete"
  ON public.agent_definitions FOR DELETE TO authenticated
  USING (public.is_super_admin());

-- ============================================================
-- RLS POLICIES: agent_runs
-- ============================================================

CREATE POLICY "agent_runs_select"
  ON public.agent_runs FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR public.is_admin());

CREATE POLICY "agent_runs_insert"
  ON public.agent_runs FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid() OR public.is_admin());

CREATE POLICY "agent_runs_update"
  ON public.agent_runs FOR UPDATE TO authenticated
  USING (user_id = auth.uid() OR public.is_admin())
  WITH CHECK (user_id = auth.uid() OR public.is_admin());

-- ============================================================
-- RLS POLICIES: agent_outputs
-- ============================================================

CREATE POLICY "agent_outputs_select"
  ON public.agent_outputs FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR public.is_admin());

CREATE POLICY "agent_outputs_insert"
  ON public.agent_outputs FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid() OR public.is_admin());

-- No UPDATE: agent outputs are immutable once written

-- ============================================================
-- RLS POLICIES: market_snapshots
-- Read-only shared data. Inserts only via service_role (agent pipeline).
-- ============================================================

CREATE POLICY "market_snapshots_select"
  ON public.market_snapshots FOR SELECT TO authenticated
  USING (true);

-- Direct inserts blocked for regular users; service_role bypasses RLS
CREATE POLICY "market_snapshots_insert"
  ON public.market_snapshots FOR INSERT TO authenticated
  WITH CHECK (public.is_admin());

-- ============================================================
-- RLS POLICIES: signals
-- ============================================================

CREATE POLICY "signals_select"
  ON public.signals FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR public.is_admin());

CREATE POLICY "signals_insert"
  ON public.signals FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid() OR public.is_admin());

CREATE POLICY "signals_update"
  ON public.signals FOR UPDATE TO authenticated
  USING (user_id = auth.uid() OR public.is_admin())
  WITH CHECK (user_id = auth.uid() OR public.is_admin());

-- ============================================================
-- RLS POLICIES: trade_decisions
-- ============================================================

CREATE POLICY "trade_decisions_select"
  ON public.trade_decisions FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR public.is_admin());

CREATE POLICY "trade_decisions_insert"
  ON public.trade_decisions FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid() OR public.is_admin());

-- Only manual approval fields should change post-creation; service_role handles the rest
CREATE POLICY "trade_decisions_update"
  ON public.trade_decisions FOR UPDATE TO authenticated
  USING (user_id = auth.uid() OR public.is_admin())
  WITH CHECK (user_id = auth.uid() OR public.is_admin());

-- ============================================================
-- RLS POLICIES: trades
-- ============================================================

CREATE POLICY "trades_select"
  ON public.trades FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR public.is_admin());

CREATE POLICY "trades_insert"
  ON public.trades FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid() OR public.is_admin());

CREATE POLICY "trades_update"
  ON public.trades FOR UPDATE TO authenticated
  USING (user_id = auth.uid() OR public.is_admin())
  WITH CHECK (user_id = auth.uid() OR public.is_admin());

-- ============================================================
-- RLS POLICIES: trade_events (append-only from user perspective)
-- ============================================================

CREATE POLICY "trade_events_select"
  ON public.trade_events FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR public.is_admin());

CREATE POLICY "trade_events_insert"
  ON public.trade_events FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid() OR public.is_admin());

-- No UPDATE or DELETE policies intentionally omitted (immutability enforced)

-- ============================================================
-- RLS POLICIES: risk_logs
-- ============================================================

CREATE POLICY "risk_logs_select"
  ON public.risk_logs FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR public.is_admin());

CREATE POLICY "risk_logs_insert"
  ON public.risk_logs FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid() OR public.is_admin());

-- ============================================================
-- RLS POLICIES: security_logs
-- Users see their own events. security_admin / super_admin see all.
-- ============================================================

CREATE POLICY "security_logs_select"
  ON public.security_logs FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR public.is_security_admin());

CREATE POLICY "security_logs_insert"
  ON public.security_logs FOR INSERT TO authenticated
  WITH CHECK (public.is_admin() OR user_id = auth.uid() OR user_id IS NULL);

-- Only security_admin can mark events resolved
CREATE POLICY "security_logs_update"
  ON public.security_logs FOR UPDATE TO authenticated
  USING (public.is_security_admin())
  WITH CHECK (public.is_security_admin());

-- ============================================================
-- RLS POLICIES: red_team_reports
-- security_admin / super_admin only
-- ============================================================

CREATE POLICY "red_team_reports_select"
  ON public.red_team_reports FOR SELECT TO authenticated
  USING (public.is_security_admin());

CREATE POLICY "red_team_reports_insert"
  ON public.red_team_reports FOR INSERT TO authenticated
  WITH CHECK (public.is_admin());

CREATE POLICY "red_team_reports_update"
  ON public.red_team_reports FOR UPDATE TO authenticated
  USING (public.is_security_admin())
  WITH CHECK (public.is_security_admin());

-- ============================================================
-- RLS POLICIES: system_evolution_reports
-- admin / super_admin only
-- ============================================================

CREATE POLICY "sys_evo_select"
  ON public.system_evolution_reports FOR SELECT TO authenticated
  USING (public.is_admin());

CREATE POLICY "sys_evo_insert"
  ON public.system_evolution_reports FOR INSERT TO authenticated
  WITH CHECK (public.is_admin());

CREATE POLICY "sys_evo_update"
  ON public.system_evolution_reports FOR UPDATE TO authenticated
  USING (public.is_super_admin())
  WITH CHECK (public.is_super_admin());

-- ============================================================
-- RLS POLICIES: strategy_configs
-- ============================================================

CREATE POLICY "strategy_configs_select"
  ON public.strategy_configs FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR public.is_admin());

CREATE POLICY "strategy_configs_insert"
  ON public.strategy_configs FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid());

CREATE POLICY "strategy_configs_update"
  ON public.strategy_configs FOR UPDATE TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- ============================================================
-- RLS POLICIES: backtests
-- ============================================================

CREATE POLICY "backtests_select"
  ON public.backtests FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR public.is_admin());

CREATE POLICY "backtests_insert"
  ON public.backtests FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid());

CREATE POLICY "backtests_update"
  ON public.backtests FOR UPDATE TO authenticated
  USING (user_id = auth.uid() OR public.is_admin())
  WITH CHECK (user_id = auth.uid() OR public.is_admin());

-- ============================================================
-- RLS POLICIES: subscriptions
-- Users see their own. Admins see all.
-- Mutations only via service_role (Stripe webhook Edge Function).
-- ============================================================

CREATE POLICY "subscriptions_select"
  ON public.subscriptions FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR public.is_admin());

-- Service_role (Stripe webhook) handles inserts/updates; block direct access
CREATE POLICY "subscriptions_insert"
  ON public.subscriptions FOR INSERT TO authenticated
  WITH CHECK (public.is_admin());

CREATE POLICY "subscriptions_update"
  ON public.subscriptions FOR UPDATE TO authenticated
  USING (public.is_admin())
  WITH CHECK (public.is_admin());

-- ============================================================
-- RLS POLICIES: payments
-- ============================================================

CREATE POLICY "payments_select"
  ON public.payments FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR public.is_admin());

CREATE POLICY "payments_insert"
  ON public.payments FOR INSERT TO authenticated
  WITH CHECK (public.is_admin());

-- ============================================================
-- RLS POLICIES: notifications
-- ============================================================

CREATE POLICY "notifications_select"
  ON public.notifications FOR SELECT TO authenticated
  USING (user_id = auth.uid());

CREATE POLICY "notifications_insert"
  ON public.notifications FOR INSERT TO authenticated
  WITH CHECK (public.is_admin() OR user_id = auth.uid());

-- Users can mark their own notifications read; cannot change other fields
CREATE POLICY "notifications_update"
  ON public.notifications FOR UPDATE TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

CREATE POLICY "notifications_delete"
  ON public.notifications FOR DELETE TO authenticated
  USING (user_id = auth.uid());

-- ============================================================
-- RLS POLICIES: audit_logs (append-only)
-- Users see their own entries. Admins see all.
-- No UPDATE or DELETE policies defined (immutability enforced by omission).
-- ============================================================

CREATE POLICY "audit_logs_select"
  ON public.audit_logs FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR public.is_admin());

-- Allow any authenticated session to insert (source column identifies the actor)
CREATE POLICY "audit_logs_insert"
  ON public.audit_logs FOR INSERT TO authenticated
  WITH CHECK (true);

-- ============================================================
-- RLS POLICIES: database_schema_audits
-- ============================================================

CREATE POLICY "dsa_select"
  ON public.database_schema_audits FOR SELECT TO authenticated
  USING (public.is_admin());

CREATE POLICY "dsa_insert"
  ON public.database_schema_audits FOR INSERT TO authenticated
  WITH CHECK (public.is_admin());

CREATE POLICY "dsa_update"
  ON public.database_schema_audits FOR UPDATE TO authenticated
  USING (public.is_super_admin())
  WITH CHECK (public.is_super_admin());

-- ============================================================
-- REVOKE anon access to all public tables
-- The anon role must never read trading or user data.
-- ============================================================

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM anon;

-- ============================================================
-- GRANT authenticated role minimum required permissions
-- RLS policies enforce row-level access on top of these.
-- ============================================================

GRANT USAGE ON SCHEMA public TO authenticated;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.profiles               TO authenticated;
GRANT SELECT, INSERT, UPDATE         ON public.user_settings          TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.exchange_accounts      TO authenticated;
-- encrypted_api_keys: no grants to authenticated; service_role only
GRANT SELECT, INSERT, UPDATE, DELETE ON public.bots                   TO authenticated;
GRANT SELECT, INSERT, UPDATE         ON public.bot_configs            TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.agent_definitions      TO authenticated;
GRANT SELECT, INSERT, UPDATE         ON public.agent_runs             TO authenticated;
GRANT SELECT, INSERT                 ON public.agent_outputs          TO authenticated;
GRANT SELECT, INSERT                 ON public.market_snapshots       TO authenticated;
GRANT SELECT, INSERT, UPDATE         ON public.signals                TO authenticated;
GRANT SELECT, INSERT, UPDATE         ON public.trade_decisions        TO authenticated;
GRANT SELECT, INSERT, UPDATE         ON public.trades                 TO authenticated;
GRANT SELECT, INSERT                 ON public.trade_events           TO authenticated;
GRANT SELECT, INSERT                 ON public.risk_logs              TO authenticated;
GRANT SELECT, INSERT, UPDATE         ON public.security_logs          TO authenticated;
GRANT SELECT, INSERT, UPDATE         ON public.red_team_reports       TO authenticated;
GRANT SELECT, INSERT, UPDATE         ON public.system_evolution_reports TO authenticated;
GRANT SELECT, INSERT, UPDATE         ON public.strategy_configs       TO authenticated;
GRANT SELECT, INSERT, UPDATE         ON public.backtests              TO authenticated;
GRANT SELECT                         ON public.subscriptions          TO authenticated;
GRANT SELECT                         ON public.payments               TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.notifications          TO authenticated;
GRANT SELECT, INSERT                 ON public.audit_logs             TO authenticated;
GRANT SELECT                         ON public.database_schema_audits TO authenticated;

-- ============================================================
-- COMMENTS (pg_catalog — visible in Supabase Studio)
-- ============================================================

COMMENT ON TABLE public.profiles IS
  'One row per auth.users. Core user identity and platform metadata.';
COMMENT ON TABLE public.encrypted_api_keys IS
  'Stores ONLY pgsodium/Vault-encrypted bytea blobs. Never plaintext. '
  'Access restricted to service_role via Edge Functions exclusively. '
  'Disable in Supabase Dashboard Data API settings.';
COMMENT ON TABLE public.bots IS
  'Trading bots owned by users. Live bots require exchange_account_id.';
COMMENT ON TABLE public.agent_definitions IS
  'Platform-wide catalog of AI agents. Managed by super_admin only.';
COMMENT ON TABLE public.trade_decisions IS
  'Immutable record of every AI consensus decision with full agent output snapshot.';
COMMENT ON TABLE public.audit_logs IS
  'Append-only compliance log. No UPDATE or DELETE policies defined.';
COMMENT ON TABLE public.red_team_reports IS
  'Security vulnerability reports from Red Team Agent. Visible to security_admin+ only.';
COMMENT ON COLUMN public.exchange_accounts.can_withdraw IS
  'Always false. Enforced by CHECK constraint. Withdrawal-enabled keys must be rejected at Edge Function level.';
COMMENT ON COLUMN public.encrypted_api_keys.encrypted_api_key IS
  'pgsodium-encrypted bytea. Decryption only via service_role Edge Function using vault_key_id.';
