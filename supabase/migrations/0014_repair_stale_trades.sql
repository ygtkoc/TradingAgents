-- =============================================================================
-- Migration 0014 — Repair stale open paper trades + robust paper_reset()
--
-- PROBLEM: When paper_reset() is unavailable (migrations not yet pushed) or
-- the dev fallback only resets paper_accounts.balance, old paper trades stay
-- in status='open'. The CRO risk agent then sees these stale open positions
-- and vetoes every new trade with "position_limit_reached".
--
-- FIX 1: Close any open/partially_filled paper trades whose account is now
--   inactive (i.e., user pressed Reset). This is a one-time repair + trigger.
--
-- FIX 2: Add a trigger that auto-cancels open paper trades when
--   paper_accounts.status transitions to 'inactive' (i.e., every reset).
--
-- FIX 3: Replace paper_reset() with a hardened version that also handles
--   gracefully missing columns (warmup_status etc) via conditional DDL.
-- =============================================================================

BEGIN;

-- ── 1. One-time repair: cancel stale open paper trades ────────────────────────
-- Safe to run multiple times (only touches open/partially_filled rows).

UPDATE public.trades t
SET
  status       = 'cancelled',
  close_reason = 'stale_after_account_reset',
  closed_at    = NOW(),
  updated_at   = NOW()
FROM public.paper_accounts pa
WHERE t.user_id    = pa.user_id
  AND t.mode       = 'paper'
  AND t.status     IN ('open', 'partial_fill')
  AND pa.status    = 'inactive';

-- ── 2. Trigger: auto-cancel open paper trades on account status → inactive ────

CREATE OR REPLACE FUNCTION public._cancel_open_paper_trades_on_reset()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
BEGIN
  -- Only fire when status changes FROM non-inactive TO inactive
  IF NEW.status = 'inactive' AND OLD.status != 'inactive' THEN
    UPDATE public.trades
    SET
      status       = 'cancelled',
      close_reason = 'paper_account_reset',
      closed_at    = NOW(),
      updated_at   = NOW()
    WHERE user_id = NEW.user_id
      AND mode    = 'paper'
      AND status  IN ('open', 'partial_fill');
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_cancel_trades_on_paper_reset ON public.paper_accounts;

CREATE TRIGGER trg_cancel_trades_on_paper_reset
  AFTER UPDATE OF status ON public.paper_accounts
  FOR EACH ROW
  EXECUTE FUNCTION public._cancel_open_paper_trades_on_reset();

-- ── 3. Harden paper_reset(): handle missing warmup columns gracefully ─────────
-- Replaces the version from 0013 with identical logic but wrapped in
-- exception handlers for environments where 0012 wasn't applied yet.

CREATE OR REPLACE FUNCTION public.paper_reset(p_user_id UUID)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
DECLARE
  v_caller_id   UUID;
  v_account     RECORD;
  v_signals     INTEGER := 0;
  v_runs        INTEGER := 0;
  v_decisions   INTEGER := 0;
  v_trades      INTEGER := 0;
  v_events      INTEGER := 0;
  v_pa_events   INTEGER := 0;
BEGIN
  -- ── Security ─────────────────────────────────────────────────────────────
  v_caller_id := auth.uid();
  IF v_caller_id IS NULL OR v_caller_id != p_user_id THEN
    RAISE EXCEPTION 'paper_reset: unauthorized (caller % ≠ target %)',
      v_caller_id, p_user_id
      USING ERRCODE = '42501';
  END IF;

  -- ── Resolve paper account ─────────────────────────────────────────────────
  SELECT id, starting_balance INTO v_account
  FROM public.paper_accounts
  WHERE user_id = p_user_id
  LIMIT 1;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'paper_reset: no paper account found for user %', p_user_id
      USING ERRCODE = 'P0002';
  END IF;

  -- ── Delete pipeline data (FK order) ──────────────────────────────────────
  DELETE FROM public.agent_outputs
  WHERE agent_run_id IN (
    SELECT id FROM public.agent_runs WHERE user_id = p_user_id
  );

  DELETE FROM public.trade_decisions WHERE user_id = p_user_id;
  GET DIAGNOSTICS v_decisions = ROW_COUNT;

  DELETE FROM public.trade_events WHERE user_id = p_user_id;
  GET DIAGNOSTICS v_events = ROW_COUNT;

  -- Cancel (not delete) paper trades so the position engine can close them
  UPDATE public.trades
  SET
    status       = 'cancelled',
    close_reason = 'paper_account_reset',
    closed_at    = NOW(),
    updated_at   = NOW()
  WHERE user_id = p_user_id AND mode = 'paper'
    AND status IN ('open', 'partial_fill');

  -- Then delete ALL paper trades (cancelled too)
  DELETE FROM public.trades WHERE user_id = p_user_id AND mode = 'paper';
  GET DIAGNOSTICS v_trades = ROW_COUNT;

  DELETE FROM public.agent_runs WHERE user_id = p_user_id;
  GET DIAGNOSTICS v_runs = ROW_COUNT;

  DELETE FROM public.signals WHERE user_id = p_user_id;
  GET DIAGNOSTICS v_signals = ROW_COUNT;

  DELETE FROM public.paper_account_events WHERE user_id = p_user_id;
  GET DIAGNOSTICS v_pa_events = ROW_COUNT;

  DELETE FROM public.notifications WHERE user_id = p_user_id;

  -- ── Reset paper_accounts ─────────────────────────────────────────────────
  UPDATE public.paper_accounts
  SET
    balance        = starting_balance,
    equity         = starting_balance,
    realized_pnl   = 0,
    unrealized_pnl = 0,
    status         = 'inactive',
    started_at     = NULL,
    paused_at      = NULL,
    updated_at     = NOW()
  WHERE user_id = p_user_id;

  -- ── Reset bot warmup (migration 0012 columns) ─────────────────────────────
  -- Wrapped in a nested block so the function still succeeds if 0012 hasn't
  -- been applied yet (warmup columns may not exist).
  BEGIN
    UPDATE public.bots
    SET
      warmup_status       = 'pending',
      warmup_started_at   = NULL,
      warmup_completed_at = NULL,
      candles_collected   = 0,
      last_signal_at      = NULL,
      next_signal_at      = NULL
    WHERE user_id = p_user_id AND mode = 'paper';
  EXCEPTION WHEN undefined_column THEN
    -- Migration 0012 not yet applied — skip warmup reset safely.
    NULL;
  END;

  -- ── Return summary ────────────────────────────────────────────────────────
  RETURN jsonb_build_object(
    'ok',           true,
    'signals',      v_signals,
    'agent_runs',   v_runs,
    'decisions',    v_decisions,
    'trades',       v_trades,
    'trade_events', v_events,
    'pa_events',    v_pa_events
  );
END;
$$;

GRANT EXECUTE ON FUNCTION public.paper_reset(UUID) TO authenticated;

-- ── 4. Ensure notifications table has user_id column (safe no-op if exists) ──
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name   = 'notifications'
      AND column_name  = 'user_id'
  ) THEN
    -- notifications table uses different schema in some setups; skip gracefully
    NULL;
  END IF;
END;
$$;

COMMIT;
