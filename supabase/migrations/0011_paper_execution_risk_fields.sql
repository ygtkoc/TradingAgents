-- =============================================================================
-- Migration 0011 — Paper execution risk fields
--
-- Adds risk-sizing columns to trades so every paper trade stores:
--   • risk_amount        — dollar risk (e.g. $20 for 2% of $1,000)
--   • risk_percent       — percentage of account risked (e.g. 2.0)
--   • risk_reward_ratio  — configured R:R (e.g. 2.0 = 2R target)
--   • r_multiple         — realised R-multiple after close (null while open)
--   • expected_reward    — risk_amount × risk_reward_ratio (e.g. $40)
--   • notional           — entry_price × quantity (position value)
--   • close_reason       — how the trade closed (take_profit / stop_loss /
--                           manual / liquidation / bot_stopped)
--
-- stop_loss and take_profit already exist on trades (from 0005).
-- All new columns are nullable so existing rows are unaffected.
-- =============================================================================

BEGIN;

ALTER TABLE public.trades
    ADD COLUMN IF NOT EXISTS risk_amount       NUMERIC(20,8),
    ADD COLUMN IF NOT EXISTS risk_percent      NUMERIC(8,4),
    ADD COLUMN IF NOT EXISTS risk_reward_ratio NUMERIC(8,4),
    ADD COLUMN IF NOT EXISTS r_multiple        NUMERIC(8,4),
    ADD COLUMN IF NOT EXISTS expected_reward   NUMERIC(20,8),
    ADD COLUMN IF NOT EXISTS notional          NUMERIC(20,8),
    ADD COLUMN IF NOT EXISTS close_reason      TEXT
        CONSTRAINT trades_close_reason_check CHECK (close_reason IN (
            'take_profit', 'stop_loss', 'manual', 'liquidation',
            'bot_stopped', 'account_depleted', 'timeout', 'cancelled'
        ));

COMMENT ON COLUMN public.trades.risk_amount IS
    'Dollar amount risked on this trade (balance × risk_percent / 100).';
COMMENT ON COLUMN public.trades.risk_percent IS
    'Percentage of account balance risked (e.g. 2.0 = 2%).';
COMMENT ON COLUMN public.trades.risk_reward_ratio IS
    'Target reward-to-risk ratio (e.g. 2.0 means TP = entry ± 2 × SL distance).';
COMMENT ON COLUMN public.trades.r_multiple IS
    'Realised R-multiple at close. Positive = winner, negative = loser. Null while open.';
COMMENT ON COLUMN public.trades.expected_reward IS
    'Expected reward if TP is hit: risk_amount × risk_reward_ratio.';
COMMENT ON COLUMN public.trades.notional IS
    'Position notional value: entry_price × quantity.';
COMMENT ON COLUMN public.trades.close_reason IS
    'Reason the trade was closed. Null while open.';

-- Index for fast closed-trade PnL queries
CREATE INDEX IF NOT EXISTS idx_trades_user_mode_status
    ON public.trades (user_id, mode, status, created_at DESC);

COMMIT;
