-- =============================================================================
-- Migration 0017 - Paper close reason repair + manual close-all helper
--
-- Fixes paper trades failing to close when lifecycle wrote a detailed sentence
-- into trades.close_reason while the DB constraint expected canonical tokens.
-- Also provides a safe authenticated helper to close all open paper positions
-- at the latest stored market price.
-- =============================================================================

BEGIN;

ALTER TABLE public.trades
  DROP CONSTRAINT IF EXISTS trades_close_reason_check;

ALTER TABLE public.trades
  ADD CONSTRAINT trades_close_reason_check CHECK (
    close_reason IS NULL OR close_reason IN (
      'take_profit',
      'stop_loss',
      'trailing_stop',
      'emergency',
      'manual',
      'liquidation',
      'bot_stopped',
      'account_depleted',
      'timeout',
      'cancelled',
      'paper_account_reset',
      'stale_after_account_reset'
    )
  );

CREATE OR REPLACE FUNCTION public.paper_close_open_trades(p_user_id UUID)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
DECLARE
  v_caller_id      UUID;
  v_account        RECORD;
  v_trade          RECORD;
  v_close_price    NUMERIC;
  v_entry_price    NUMERIC;
  v_qty            NUMERIC;
  v_realized       NUMERIC;
  v_pnl_pct        NUMERIC;
  v_reserved       NUMERIC;
  v_delta          NUMERIC;
  v_balance        NUMERIC;
  v_realized_total NUMERIC;
  v_closed         INTEGER := 0;
BEGIN
  v_caller_id := auth.uid();
  IF v_caller_id IS NULL OR v_caller_id != p_user_id THEN
    RAISE EXCEPTION 'paper_close_open_trades: unauthorized (caller %, target %)',
      v_caller_id, p_user_id
      USING ERRCODE = '42501';
  END IF;

  SELECT * INTO v_account
  FROM public.paper_accounts
  WHERE user_id = p_user_id
  LIMIT 1
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'paper_close_open_trades: no paper account found for user %', p_user_id
      USING ERRCODE = 'P0002';
  END IF;

  v_balance := COALESCE(v_account.balance, 0);
  v_realized_total := COALESCE(v_account.realized_pnl, 0);

  FOR v_trade IN
    SELECT *
    FROM public.trades
    WHERE user_id = p_user_id
      AND mode = 'paper'
      AND status IN ('open', 'partial_fill')
    ORDER BY created_at ASC
  LOOP
    SELECT ms.close_price INTO v_close_price
    FROM public.market_snapshots ms
    WHERE ms.exchange = v_trade.exchange
      AND ms.symbol = v_trade.symbol
    ORDER BY ms.captured_at DESC
    LIMIT 1;

    v_entry_price := COALESCE(v_trade.avg_fill_price, v_trade.entry_price, 0);
    v_close_price := COALESCE(NULLIF(v_close_price, 0), v_trade.exit_price, v_entry_price);
    v_qty := COALESCE(NULLIF(v_trade.filled_quantity, 0), v_trade.quantity, 0);

    IF v_entry_price <= 0 OR v_close_price <= 0 OR v_qty <= 0 THEN
      CONTINUE;
    END IF;

    IF v_trade.direction = 'long' THEN
      v_realized := (v_close_price - v_entry_price) * v_qty;
    ELSE
      v_realized := (v_entry_price - v_close_price) * v_qty;
    END IF;

    v_pnl_pct := CASE
      WHEN (v_entry_price * v_qty) > 0 THEN (v_realized / (v_entry_price * v_qty)) * 100
      ELSE 0
    END;

    v_reserved := COALESCE(
      NULLIF((v_trade.metadata ->> 'reserved_amount')::NUMERIC, 0),
      NULLIF((v_trade.metadata ->> 'notional')::NUMERIC, 0),
      NULLIF(v_trade.notional, 0),
      v_entry_price * v_qty
    );
    v_delta := v_reserved + v_realized;
    v_balance := v_balance + v_delta;
    v_realized_total := v_realized_total + v_realized;

    UPDATE public.trades
    SET
      status = 'closed',
      lifecycle_status = 'closed',
      lifecycle_worker_id = NULL,
      lifecycle_claimed_at = NULL,
      lifecycle_last_checked_at = NOW(),
      closed_at = NOW(),
      exit_price = v_close_price,
      avg_exit_price = v_close_price,
      realized_pnl = v_realized,
      unrealized_pnl = NULL,
      pnl = v_realized,
      pnl_pct = v_pnl_pct,
      close_reason = 'manual',
      updated_at = NOW()
    WHERE id = v_trade.id;

    INSERT INTO public.trade_events (
      trade_id,
      trade_decision_id,
      bot_id,
      user_id,
      event_type,
      details
    )
    VALUES (
      v_trade.id,
      v_trade.trade_decision_id,
      v_trade.bot_id,
      v_trade.user_id,
      'manual_paper_close',
      jsonb_build_object(
        'close_price', v_close_price,
        'realized_pnl', v_realized,
        'pnl_pct', v_pnl_pct,
        'reserved_returned', v_reserved
      )
    );

    INSERT INTO public.paper_account_events (
      account_id,
      user_id,
      trade_id,
      event_type,
      delta,
      realized_delta,
      unrealized_delta,
      balance_after,
      realized_after,
      unrealized_after,
      note,
      metadata
    )
    VALUES (
      v_account.id,
      p_user_id,
      v_trade.id,
      'trade_close_settle',
      v_delta,
      v_realized,
      0,
      v_balance,
      v_realized_total,
      0,
      'manual close ' || v_trade.symbol,
      jsonb_build_object(
        'symbol', v_trade.symbol,
        'direction', v_trade.direction,
        'entry', v_entry_price,
        'exit', v_close_price,
        'quantity', v_qty,
        'reserved_returned', v_reserved,
        'realized_pnl', v_realized,
        'source', 'paper_close_open_trades'
      )
    );

    v_closed := v_closed + 1;
  END LOOP;

  UPDATE public.paper_accounts
  SET
    balance = v_balance,
    realized_pnl = v_realized_total,
    unrealized_pnl = 0,
    updated_at = NOW()
  WHERE id = v_account.id;

  RETURN jsonb_build_object(
    'ok', true,
    'closed', v_closed,
    'balance', v_balance,
    'realized_pnl', v_realized_total
  );
END;
$$;

GRANT EXECUTE ON FUNCTION public.paper_close_open_trades(UUID) TO authenticated;

COMMIT;
