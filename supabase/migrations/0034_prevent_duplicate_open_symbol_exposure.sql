-- =============================================================================
-- Migration 0034 - Prevent duplicate open symbol exposure
--
-- A worker restart or concurrent execution race must not be able to open the
-- same symbol twice for the same user/mode. Keep the application guard, but
-- enforce the invariant at the database layer too.
-- =============================================================================

BEGIN;

WITH ranked AS (
  SELECT
    id,
    row_number() OVER (
      PARTITION BY user_id, COALESCE(mode, 'paper'), upper(replace(symbol, '/', ''))
      ORDER BY created_at ASC, id ASC
    ) AS rn
  FROM public.trades
  WHERE status = 'open'
)
UPDATE public.trades AS t
SET
  status = 'cancelled',
  lifecycle_status = 'closed',
  closed_at = COALESCE(t.closed_at, now()),
  close_reason = COALESCE(t.close_reason, 'cancelled'),
  metadata = COALESCE(t.metadata, '{}'::jsonb) || jsonb_build_object(
    'duplicate_symbol_exposure_cancelled_at', now(),
    'duplicate_symbol_exposure_policy', 'one_open_trade_per_user_mode_symbol'
  )
FROM ranked AS r
WHERE t.id = r.id
  AND r.rn > 1;

CREATE UNIQUE INDEX IF NOT EXISTS trades_one_open_symbol_per_user_mode_idx
  ON public.trades (user_id, COALESCE(mode, 'paper'), upper(replace(symbol, '/', '')))
  WHERE status = 'open';

COMMENT ON INDEX public.trades_one_open_symbol_per_user_mode_idx IS
  'Prevents concurrent workers from opening duplicate active exposure on the same normalized symbol for a user/mode.';

COMMIT;
