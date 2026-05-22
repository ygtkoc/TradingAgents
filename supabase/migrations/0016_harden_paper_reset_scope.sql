-- =============================================================================
-- Migration 0016 - Harden paper_reset() scope and starting-balance handling
--
-- The reset contract is:
--   - clear the caller's paper-mode runtime state
--   - keep live/shadow rows, bots, exchange connections, and settings intact
--   - reset the paper account balance/PnL and leave the account paused
--
-- This replaces the earlier single-argument function so the frontend and Edge
-- Function can both pass an optional new starting balance atomically.
-- =============================================================================

BEGIN;

DROP FUNCTION IF EXISTS public.paper_reset(UUID);
DROP FUNCTION IF EXISTS public.paper_reset(UUID, NUMERIC);

CREATE OR REPLACE FUNCTION public.paper_reset(
  p_user_id UUID,
  p_starting_balance NUMERIC DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
DECLARE
  v_caller_id        UUID;
  v_account          RECORD;
  v_reset_balance    NUMERIC;
  v_paper_bot_ids    UUID[];
  v_decision_ids     UUID[];
  v_trade_ids        UUID[];
  v_agent_run_ids    UUID[];
  v_signals          INTEGER := 0;
  v_agent_runs       INTEGER := 0;
  v_agent_outputs    INTEGER := 0;
  v_decisions        INTEGER := 0;
  v_trades           INTEGER := 0;
  v_trade_events     INTEGER := 0;
  v_account_events   INTEGER := 0;
BEGIN
  v_caller_id := auth.uid();
  IF v_caller_id IS NULL OR v_caller_id != p_user_id THEN
    RAISE EXCEPTION 'paper_reset: unauthorized (caller %, target %)',
      v_caller_id, p_user_id
      USING ERRCODE = '42501';
  END IF;

  SELECT id, starting_balance INTO v_account
  FROM public.paper_accounts
  WHERE user_id = p_user_id
  LIMIT 1;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'paper_reset: no paper account found for user %', p_user_id
      USING ERRCODE = 'P0002';
  END IF;

  IF p_starting_balance IS NULL THEN
    v_reset_balance := v_account.starting_balance;
  ELSIF p_starting_balance > 0 AND p_starting_balance <= 1000000 THEN
    v_reset_balance := p_starting_balance;
  ELSE
    RAISE EXCEPTION 'paper_reset: starting_balance must be greater than 0 and at most 1000000'
      USING ERRCODE = '22023';
  END IF;

  SELECT COALESCE(array_agg(id), ARRAY[]::UUID[]) INTO v_paper_bot_ids
  FROM public.bots
  WHERE user_id = p_user_id
    AND mode = 'paper';

  SELECT COALESCE(array_agg(id), ARRAY[]::UUID[]) INTO v_decision_ids
  FROM public.trade_decisions
  WHERE user_id = p_user_id
    AND (
      mode = 'paper'
      OR bot_id = ANY(v_paper_bot_ids)
    );

  SELECT COALESCE(array_agg(id), ARRAY[]::UUID[]) INTO v_trade_ids
  FROM public.trades
  WHERE user_id = p_user_id
    AND mode = 'paper';

  SELECT COALESCE(array_agg(id), ARRAY[]::UUID[]) INTO v_agent_run_ids
  FROM public.agent_runs
  WHERE user_id = p_user_id
    AND (
      bot_id = ANY(v_paper_bot_ids)
      OR trade_decision_id = ANY(v_decision_ids)
    );

  -- Break restrictive cross-links before deleting parents.
  UPDATE public.trade_decisions
  SET linked_trade_id = NULL
  WHERE id = ANY(v_decision_ids);

  UPDATE public.trades
  SET trade_decision_id = NULL
  WHERE id = ANY(v_trade_ids);

  DELETE FROM public.trade_events
  WHERE user_id = p_user_id
    AND (
      trade_id = ANY(v_trade_ids)
      OR trade_decision_id = ANY(v_decision_ids)
      OR bot_id = ANY(v_paper_bot_ids)
    );
  GET DIAGNOSTICS v_trade_events = ROW_COUNT;

  DELETE FROM public.trades
  WHERE id = ANY(v_trade_ids);
  GET DIAGNOSTICS v_trades = ROW_COUNT;

  DELETE FROM public.trade_decisions
  WHERE id = ANY(v_decision_ids);
  GET DIAGNOSTICS v_decisions = ROW_COUNT;

  DELETE FROM public.signals
  WHERE user_id = p_user_id
    AND bot_id = ANY(v_paper_bot_ids);
  GET DIAGNOSTICS v_signals = ROW_COUNT;

  DELETE FROM public.agent_outputs
  WHERE user_id = p_user_id
    AND agent_run_id = ANY(v_agent_run_ids);
  GET DIAGNOSTICS v_agent_outputs = ROW_COUNT;

  DELETE FROM public.agent_runs
  WHERE id = ANY(v_agent_run_ids);
  GET DIAGNOSTICS v_agent_runs = ROW_COUNT;

  DELETE FROM public.paper_account_events
  WHERE user_id = p_user_id;
  GET DIAGNOSTICS v_account_events = ROW_COUNT;

  UPDATE public.paper_accounts
  SET
    starting_balance = v_reset_balance,
    balance          = v_reset_balance,
    realized_pnl     = 0,
    unrealized_pnl   = 0,
    status           = 'paused',
    reset_at         = NOW(),
    started_at       = NULL,
    paused_at        = NOW(),
    updated_at       = NOW(),
    metadata         = COALESCE(metadata, '{}'::jsonb)
                       || jsonb_build_object('last_reset_via', 'paper_reset_rpc')
  WHERE user_id = p_user_id;

  BEGIN
    UPDATE public.bots
    SET
      warmup_status       = 'pending',
      warmup_started_at   = NULL,
      warmup_completed_at = NULL,
      candles_collected   = 0,
      last_signal_at      = NULL,
      next_signal_at      = NULL,
      updated_at          = NOW()
    WHERE user_id = p_user_id
      AND mode = 'paper';
  EXCEPTION WHEN undefined_column THEN
    NULL;
  END;

  RETURN jsonb_build_object(
    'account_id',       v_account.id,
    'starting_balance', v_reset_balance,
    'status',           'paused',
    'deleted',          jsonb_build_object(
      'signals',         v_signals,
      'agent_runs',      v_agent_runs,
      'agent_outputs',   v_agent_outputs,
      'decisions',       v_decisions,
      'trades',          v_trades,
      'events',          v_trade_events,
      'account_events',  v_account_events
    )
  );
END;
$$;

GRANT EXECUTE ON FUNCTION public.paper_reset(UUID, NUMERIC) TO authenticated;

COMMIT;
