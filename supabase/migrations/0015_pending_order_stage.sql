-- Repair order-stage trades that were previously stored as open positions.
-- A trade is a real open position only after it has a positive filled_quantity.

WITH paper_refunds AS (
  SELECT
    user_id,
    SUM(COALESCE(risk_amount, 0)) AS refund_amount
  FROM public.trades
  WHERE status = 'open'
    AND mode = 'paper'
    AND COALESCE(filled_quantity, 0) = 0
    AND COALESCE(risk_amount, 0) > 0
    AND COALESCE(metadata->>'reserved_on_open', 'true') <> 'false'
    AND metadata->>'order_stage_repaired_at' IS NULL
  GROUP BY user_id
),
updated_accounts AS (
  UPDATE public.paper_accounts pa
  SET balance = pa.balance + pr.refund_amount
  FROM paper_refunds pr
  WHERE pa.user_id = pr.user_id
  RETURNING pa.id, pa.user_id, pa.balance
),
candidate_trades AS (
  SELECT
    id,
    user_id,
    mode,
    COALESCE(risk_amount, 0) AS risk_amount
  FROM public.trades
  WHERE status = 'open'
    AND COALESCE(filled_quantity, 0) = 0
    AND metadata->>'order_stage_repaired_at' IS NULL
),
updated_trades AS (
  UPDATE public.trades t
  SET
    status = 'pending',
    metadata = COALESCE(t.metadata, '{}'::jsonb) || jsonb_build_object(
      'order_stage_repaired_at', NOW(),
      'reserved_on_open', false
    )
  FROM candidate_trades c
  WHERE t.id = c.id
  RETURNING t.id, t.user_id, t.mode, c.risk_amount
)
INSERT INTO public.paper_account_events (
  account_id,
  user_id,
  trade_id,
  event_type,
  delta,
  realized_delta,
  unrealized_delta,
  balance_after,
  note,
  metadata
)
SELECT
  ua.id,
  ut.user_id,
  ut.id,
  'pending_order_refund',
  ut.risk_amount,
  0,
  0,
  ua.balance,
  'Refund reserved paper risk for order-stage trade',
  jsonb_build_object('trade_id', ut.id, 'repair', '0015_pending_order_stage')
FROM updated_trades ut
JOIN updated_accounts ua ON ua.user_id = ut.user_id
WHERE ut.mode = 'paper'
  AND ut.risk_amount > 0;
