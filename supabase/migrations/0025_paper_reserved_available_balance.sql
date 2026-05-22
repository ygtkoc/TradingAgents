-- Migration 0025 - Split paper wallet balance into total, reserved, and available.
--
-- balance           = total paper wallet cash, including funds tied to open trades
-- reserved_balance  = funds currently reserved by open paper trades
-- available_balance = balance - reserved_balance
-- equity            = balance + unrealized_pnl

BEGIN;

ALTER TABLE public.paper_accounts
  ADD COLUMN IF NOT EXISTS reserved_balance NUMERIC(20, 8) NOT NULL DEFAULT 0;

ALTER TABLE public.paper_accounts
  DROP COLUMN IF EXISTS available_balance;

ALTER TABLE public.paper_accounts
  ADD COLUMN available_balance NUMERIC(20, 8)
  GENERATED ALWAYS AS (balance - reserved_balance) STORED;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'paper_accounts_reserved_balance_nonneg'
  ) THEN
    ALTER TABLE public.paper_accounts
      ADD CONSTRAINT paper_accounts_reserved_balance_nonneg
      CHECK (reserved_balance >= 0);
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'paper_accounts_available_balance_nonneg'
  ) THEN
    ALTER TABLE public.paper_accounts
      ADD CONSTRAINT paper_accounts_available_balance_nonneg
      CHECK (balance - reserved_balance >= 0);
  END IF;
END $$;

WITH open_reserves AS (
  SELECT
    user_id,
    SUM(
      COALESCE(
        NULLIF((metadata ->> 'reserved_amount')::NUMERIC, 0),
        NULLIF(risk_amount, 0),
        0
      )
    ) AS reserved
  FROM public.trades
  WHERE mode = 'paper'
    AND status IN ('open', 'partial_fill')
    AND COALESCE(metadata ->> 'reserved_on_open', 'true') <> 'false'
  GROUP BY user_id
)
UPDATE public.paper_accounts pa
SET
  balance = pa.balance + COALESCE(orx.reserved, 0),
  reserved_balance = COALESCE(orx.reserved, 0)
FROM open_reserves orx
WHERE pa.user_id = orx.user_id
  AND pa.reserved_balance = 0
  AND COALESCE(orx.reserved, 0) > 0;

UPDATE public.paper_accounts pa
SET reserved_balance = 0
WHERE NOT EXISTS (
  SELECT 1
  FROM public.trades t
  WHERE t.user_id = pa.user_id
    AND t.mode = 'paper'
    AND t.status IN ('open', 'partial_fill')
);

COMMENT ON COLUMN public.paper_accounts.balance IS
  'Total paper wallet cash, including funds reserved by open paper trades.';

COMMENT ON COLUMN public.paper_accounts.reserved_balance IS
  'Paper funds reserved for currently open trades.';

COMMENT ON COLUMN public.paper_accounts.available_balance IS
  'Generated free balance available for new paper trades: balance - reserved_balance.';

CREATE OR REPLACE FUNCTION public.fn_clear_stale_paper_reserved_balance()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.reserved_balance > 0
     AND NEW.reserved_balance <= OLD.reserved_balance
     AND NOT EXISTS (
    SELECT 1
    FROM public.trades t
    WHERE t.user_id = NEW.user_id
      AND t.mode = 'paper'
      AND t.status IN ('open', 'partial_fill')
  ) THEN
    NEW.reserved_balance := 0;
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_clear_stale_paper_reserved_balance ON public.paper_accounts;
CREATE TRIGGER trg_clear_stale_paper_reserved_balance
  BEFORE UPDATE ON public.paper_accounts
  FOR EACH ROW
  EXECUTE FUNCTION public.fn_clear_stale_paper_reserved_balance();

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
  v_balance        NUMERIC;
  v_reserved_total NUMERIC;
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
  v_reserved_total := COALESCE(v_account.reserved_balance, 0);
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

    v_entry_price := COALESCE(v_trade.avg_entry_price, v_trade.entry_price, 0);
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
      NULLIF(v_trade.risk_amount, 0),
      0
    );

    v_balance := v_balance + v_realized;
    v_reserved_total := GREATEST(0, v_reserved_total - v_reserved);
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
      v_realized,
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
        'reserved_after', v_reserved_total,
        'available_after', v_balance - v_reserved_total,
        'realized_pnl', v_realized,
        'source', 'paper_close_open_trades'
      )
    );

    v_closed := v_closed + 1;
  END LOOP;

  UPDATE public.paper_accounts
  SET
    balance = v_balance,
    reserved_balance = v_reserved_total,
    realized_pnl = v_realized_total,
    unrealized_pnl = 0,
    updated_at = NOW()
  WHERE id = v_account.id;

  RETURN jsonb_build_object(
    'ok', true,
    'closed', v_closed,
    'balance', v_balance,
    'reserved_balance', v_reserved_total,
    'available_balance', v_balance - v_reserved_total,
    'realized_pnl', v_realized_total
  );
END;
$$;

GRANT EXECUTE ON FUNCTION public.paper_close_open_trades(UUID) TO authenticated;

COMMIT;
