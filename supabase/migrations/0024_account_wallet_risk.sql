-- Account-wide wallet risk replaces bot-level per-trade risk.
ALTER TABLE public.user_settings
  ALTER COLUMN default_risk_per_trade_pct SET DEFAULT 2.00;

UPDATE public.user_settings
SET default_risk_per_trade_pct = 2.00
WHERE default_risk_per_trade_pct IS NULL
   OR default_risk_per_trade_pct = 1.00;
