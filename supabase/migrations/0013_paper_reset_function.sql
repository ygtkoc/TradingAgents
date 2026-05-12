-- =============================================================================
-- Migration 0013 — paper_reset() stored procedure
--
-- Provides a single atomic "reset paper trading" operation callable by the
-- authenticated Supabase client (no service_role key required in the browser).
--
-- SECURITY DEFINER means the function runs with the privileges of its OWNER
-- (the database superuser / postgres role), bypassing RLS. The first statement
-- inside the function checks that the caller is resetting ONLY their own data.
--
-- Tables cleared (in safe delete order):
--   1. agent_outputs      — via agent_run_id fk (may CASCADE; also explicit)
--   2. trade_decisions    — user_id direct
--   3. trade_events       — user_id direct
--   4. trades             — user_id + mode='paper' (never touches live trades)
--   5. agent_runs         — user_id direct
--   6. signals            — user_id direct
--   7. paper_account_events — user_id direct
--   8. notifications      — user_id direct (paper trading notifications)
-- Then resets paper_accounts and bots warmup state.
-- =============================================================================

BEGIN;

CREATE OR REPLACE FUNCTION public.paper_reset(p_user_id UUID)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
DECLARE
  v_caller_id   UUID;
  v_account     RECORD;
  v_deleted     jsonb := '{}'::jsonb;
  v_signals     INTEGER;
  v_runs        INTEGER;
  v_decisions   INTEGER;
  v_trades      INTEGER;
  v_events      INTEGER;
  v_pa_events   INTEGER;
BEGIN
  -- ── 1. Security: caller may only reset their own account ─────────────────
  v_caller_id := auth.uid();
  IF v_caller_id IS NULL OR v_caller_id != p_user_id THEN
    RAISE EXCEPTION 'paper_reset: unauthorized (caller % ≠ target %)',
      v_caller_id, p_user_id
      USING ERRCODE = '42501';
  END IF;

  -- ── 2. Resolve paper account ─────────────────────────────────────────────
  SELECT id, starting_balance INTO v_account
  FROM public.paper_accounts
  WHERE user_id = p_user_id
  LIMIT 1;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'paper_reset: no paper account found for user %', p_user_id
      USING ERRCODE = 'P0002';
  END IF;

  -- ── 3. Delete agent_outputs first (FK child of agent_runs) ───────────────
  DELETE FROM public.agent_outputs
  WHERE agent_run_id IN (
    SELECT id FROM public.agent_runs WHERE user_id = p_user_id
  );

  -- ── 4. Delete trade_decisions ─────────────────────────────────────────────
  DELETE FROM public.trade_decisions WHERE user_id = p_user_id;
  GET DIAGNOSTICS v_decisions = ROW_COUNT;

  -- ── 5. Delete trade_events ────────────────────────────────────────────────
  DELETE FROM public.trade_events WHERE user_id = p_user_id;
  GET DIAGNOSTICS v_events = ROW_COUNT;

  -- ── 6. Delete paper trades only ──────────────────────────────────────────
  DELETE FROM public.trades WHERE user_id = p_user_id AND mode = 'paper';
  GET DIAGNOSTICS v_trades = ROW_COUNT;

  -- ── 7. Delete agent_runs ─────────────────────────────────────────────────
  DELETE FROM public.agent_runs WHERE user_id = p_user_id;
  GET DIAGNOSTICS v_runs = ROW_COUNT;

  -- ── 8. Delete signals ────────────────────────────────────────────────────
  DELETE FROM public.signals WHERE user_id = p_user_id;
  GET DIAGNOSTICS v_signals = ROW_COUNT;

  -- ── 9. Delete paper_account_events ───────────────────────────────────────
  DELETE FROM public.paper_account_events WHERE user_id = p_user_id;
  GET DIAGNOSTICS v_pa_events = ROW_COUNT;

  -- ── 10. Delete notifications ──────────────────────────────────────────────
  DELETE FROM public.notifications
  WHERE user_id = p_user_id;

  -- ── 11. Reset paper_accounts ──────────────────────────────────────────────
  UPDATE public.paper_accounts
  SET
    balance          = starting_balance,
    equity           = starting_balance,
    realized_pnl     = 0,
    unrealized_pnl   = 0,
    status           = 'inactive',
    started_at       = NULL,
    paused_at        = NULL,
    updated_at       = NOW()
  WHERE user_id = p_user_id;

  -- ── 12. Reset bot warmup state ────────────────────────────────────────────
  UPDATE public.bots
  SET
    warmup_status       = 'pending',
    warmup_started_at   = NULL,
    warmup_completed_at = NULL,
    candles_collected   = 0,
    last_signal_at      = NULL,
    next_signal_at      = NULL
  WHERE user_id = p_user_id AND mode = 'paper';

  -- ── 13. Return summary ────────────────────────────────────────────────────
  RETURN jsonb_build_object(
    'ok',          true,
    'signals',     v_signals,
    'agent_runs',  v_runs,
    'decisions',   v_decisions,
    'trades',      v_trades,
    'trade_events', v_events,
    'pa_events',   v_pa_events
  );
END;
$$;

-- Grant execute to authenticated users (they can only reset their own data
-- because the function verifies auth.uid() = p_user_id internally).
GRANT EXECUTE ON FUNCTION public.paper_reset(UUID) TO authenticated;

COMMIT;
