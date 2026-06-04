-- Restore backwards-compatible aggregate PnL column expected by older
-- execution/lifecycle code and SQL helper functions.
ALTER TABLE public.trades
  ADD COLUMN IF NOT EXISTS pnl NUMERIC(20, 8);

UPDATE public.trades
SET pnl = COALESCE(realized_pnl, unrealized_pnl, pnl)
WHERE pnl IS NULL
  AND (realized_pnl IS NOT NULL OR unrealized_pnl IS NOT NULL);
