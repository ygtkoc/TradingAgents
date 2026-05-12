-- =============================================================================
-- Migration 0012 — Bot risk model, warmup tracking, cadence timestamps
--
-- Adds first-class columns for:
--   strategy_type       — scalping | momentum | trend_following | mean_reversion | balanced
--   risk_model          — percentage | fixed_usd
--   risk_value          — 2.0 (percent) or 50.0 (USD), used with risk_model
--   risk_reward_ratio   — default 2.0 (1R risked : 2R target)
--   last_signal_at      — when this bot last seeded a signal (per autonomous tick)
--   next_signal_at      — estimated next signal time (last + cooldown)
--   warmup_status       — pending | warming_up | ready
--   warmup_started_at   — when the warmup began
--   warmup_completed_at — when candles_collected >= candles_required
--   candles_collected   — count of available historical candles
--   candles_required    — threshold before trading resumes (strategy-specific)
-- =============================================================================

BEGIN;

-- ── Bot columns ───────────────────────────────────────────────────────────────

ALTER TABLE public.bots
  ADD COLUMN IF NOT EXISTS strategy_type       TEXT DEFAULT 'balanced',
  ADD COLUMN IF NOT EXISTS risk_model          TEXT DEFAULT 'percentage'
    CONSTRAINT bots_risk_model_check
      CHECK (risk_model IN ('percentage', 'fixed_usd')),
  ADD COLUMN IF NOT EXISTS risk_value          NUMERIC(20,8) DEFAULT 2.0,
  ADD COLUMN IF NOT EXISTS risk_reward_ratio   NUMERIC(8,4)  DEFAULT 2.0,
  ADD COLUMN IF NOT EXISTS last_signal_at      TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS next_signal_at      TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS warmup_status       TEXT DEFAULT 'pending'
    CONSTRAINT bots_warmup_status_check
      CHECK (warmup_status IN ('pending', 'warming_up', 'ready')),
  ADD COLUMN IF NOT EXISTS warmup_started_at   TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS warmup_completed_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS candles_collected   INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS candles_required    INTEGER DEFAULT 100;

-- ── Backfill strategy_type from metadata->>'strategy' ────────────────────────

UPDATE public.bots
SET strategy_type = COALESCE(
  NULLIF(TRIM(metadata->>'strategy'), ''),
  'balanced'
)
WHERE strategy_type = 'balanced' OR strategy_type IS NULL;

-- ── Set strategy-specific candles_required ───────────────────────────────────
-- Scalping requires fewer bars (14-period ATR needs ~20+ but 50 gives room);
-- all other strategies need 100 bars for trend detection.

UPDATE public.bots
SET candles_required = CASE
  WHEN strategy_type = 'scalping' THEN 50
  ELSE 100
END;

-- ── Comments ─────────────────────────────────────────────────────────────────

COMMENT ON COLUMN public.bots.strategy_type IS
  'Trading strategy. Determines signal cadence and candle warmup requirements.';
COMMENT ON COLUMN public.bots.risk_model IS
  'How risk_value is interpreted: percentage = % of balance, fixed_usd = dollar amount.';
COMMENT ON COLUMN public.bots.risk_value IS
  'Risk per trade. 2.0 means 2% (percentage model) or $2.00 (fixed_usd model).';
COMMENT ON COLUMN public.bots.risk_reward_ratio IS
  'Target R:R. 2.0 means take_profit = entry ± 2 × stop_distance.';
COMMENT ON COLUMN public.bots.last_signal_at IS
  'Timestamp of the last signal seeded for this bot by the autonomous engine.';
COMMENT ON COLUMN public.bots.next_signal_at IS
  'Estimated timestamp of the next signal (last_signal_at + strategy cadence).';
COMMENT ON COLUMN public.bots.warmup_status IS
  'pending: not yet started, warming_up: collecting history, ready: enough bars.';
COMMENT ON COLUMN public.bots.candles_collected IS
  'Number of closed candles available in market_snapshots for this bot''s symbols.';
COMMENT ON COLUMN public.bots.candles_required IS
  'Minimum closed candles needed before the risk agent will approve trades.';

COMMIT;
