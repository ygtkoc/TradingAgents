-- =============================================================================
-- Migration: 0006_platform_settings_and_lifecycle.sql
-- Purpose:   Platform kill-switch settings table + lifecycle monitoring columns
--            on trades for the Position & Trade Lifecycle Engine.
--
-- Changes:
--   1. platform_settings table  (global kill-switch, feature flags)
--   2. Lifecycle columns on trades
--   3. Indexes for lifecycle polling and stuck-claim recovery
--   4. release_stuck_lifecycle_claims() for pg_cron
--   5. RLS: platform_settings is service_role-only
--
-- Safety guarantees:
--   - All columns use IF NOT EXISTS / ADD COLUMN IF NOT EXISTS (re-runnable).
--   - platform_settings uses TEXT keys + JSONB values so new flags need no DDL.
--   - Lifecycle status is a TEXT CHECK column (not enum) to allow zero-downtime adds.
--   - RLS denies ALL authenticated access to platform_settings; only service_role
--     (used by Edge Functions and backend services) can read or write.
-- =============================================================================

BEGIN;

-- ── 1. platform_settings ─────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS platform_settings (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    key         TEXT        UNIQUE NOT NULL,
    value       JSONB       NOT NULL,
    description TEXT,
    updated_by  UUID        REFERENCES auth.users(id) ON DELETE SET NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE platform_settings IS
    'Global platform feature flags and kill switches. '
    'Readable only by service_role (backend) and admin Edge Functions. '
    'Users and frontend cannot access this table.';

-- Seed required keys (idempotent)
INSERT INTO platform_settings (key, value, description) VALUES
    ('global_trading_enabled',
     'true'::jsonb,
     'Master kill switch. false = halt all new executions and trigger emergency close evaluation.'),

    ('live_execution_enabled',
     'false'::jsonb,
     'DB-level live execution gate. Must be true AND ENABLE_LIVE_EXECUTION=true env var to place real orders.'),

    ('emergency_close_enabled',
     'true'::jsonb,
     'Allow lifecycle engine to submit emergency close orders for live positions. false = pause monitoring instead of closing.'),

    ('max_allowed_slippage_pct',
     '1.0'::jsonb,
     'Maximum allowed slippage % for order confirmation. Orders exceeding this write high-severity risk_log.')
ON CONFLICT (key) DO NOTHING;

-- RLS: deny all authenticated user access — service_role bypasses RLS
ALTER TABLE platform_settings ENABLE ROW LEVEL SECURITY;

-- No SELECT for authenticated users
CREATE POLICY "platform_settings_no_user_select"
    ON platform_settings FOR SELECT
    TO authenticated
    USING (false);

-- No INSERT/UPDATE/DELETE for authenticated users
CREATE POLICY "platform_settings_no_user_write"
    ON platform_settings FOR ALL
    TO authenticated
    USING (false)
    WITH CHECK (false);


-- ── 2. Lifecycle columns on trades ────────────────────────────────────────────

-- lifecycle_status: tracks where the trade is in the position monitoring FSM.
--   idle                — waiting to be claimed for monitoring
--   monitoring          — currently held by a worker for lifecycle evaluation
--   closing             — close order submitted, awaiting confirmation
--   closed              — lifecycle complete (mirrors trades.status='closed')
--   failed              — lifecycle error, needs human review
--   needs_reconciliation — exchange state unknown, do not auto-retry
ALTER TABLE trades
    ADD COLUMN IF NOT EXISTS lifecycle_status         TEXT        NOT NULL DEFAULT 'idle'
        CONSTRAINT chk_lifecycle_status CHECK (
            lifecycle_status IN (
                'idle','monitoring','closing','closed','failed','needs_reconciliation'
            )
        ),
    ADD COLUMN IF NOT EXISTS lifecycle_worker_id      TEXT        DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS lifecycle_claimed_at     TIMESTAMPTZ DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS lifecycle_last_checked_at TIMESTAMPTZ DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS lifecycle_error          TEXT        DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS lifecycle_retry_count    INT         NOT NULL DEFAULT 0,

    -- Price tracking for trailing stop
    ADD COLUMN IF NOT EXISTS trailing_stop_price      NUMERIC(20,8) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS highest_price_seen       NUMERIC(20,8) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS lowest_price_seen        NUMERIC(20,8) DEFAULT NULL,

    -- Close metadata
    ADD COLUMN IF NOT EXISTS close_reason             TEXT        DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS close_order_id           TEXT        DEFAULT NULL,

    -- P&L (unrealized updated each cycle; realized set on close)
    ADD COLUMN IF NOT EXISTS unrealized_pnl           NUMERIC(20,8) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS realized_pnl             NUMERIC(20,8) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS exit_price               NUMERIC(20,8) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS avg_exit_price           NUMERIC(20,8) DEFAULT NULL;

-- Backfill existing open trades to idle
UPDATE trades
    SET lifecycle_status = 'idle'
    WHERE status = 'open'
      AND lifecycle_status IS NULL;


-- ── 3. Indexes ────────────────────────────────────────────────────────────────

-- Fast poll for claimable open trades
CREATE INDEX IF NOT EXISTS idx_trades_lifecycle_claimable
    ON trades (created_at ASC)
    WHERE status = 'open'
      AND lifecycle_status IN ('idle', 'needs_reconciliation');

-- Stuck monitoring/closing claims (for pg_cron release)
CREATE INDEX IF NOT EXISTS idx_trades_lifecycle_stuck
    ON trades (lifecycle_claimed_at ASC)
    WHERE lifecycle_status IN ('monitoring', 'closing')
      AND status = 'open';

-- Live open trades (for reconciliation queries)
CREATE INDEX IF NOT EXISTS idx_trades_live_open
    ON trades (mode, created_at ASC)
    WHERE mode = 'live'
      AND status = 'open';

-- ── 4. release_stuck_lifecycle_claims ─────────────────────────────────────────

CREATE OR REPLACE FUNCTION release_stuck_lifecycle_claims(
    max_age_minutes  INT DEFAULT 10,
    max_retry_count  INT DEFAULT 3
)
RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    affected INT;
BEGIN
    -- Reset rows stuck in monitoring/closing back to idle (or needs_reconciliation after max retries).
    -- Called by pg_cron every 5 minutes:
    --   SELECT cron.schedule(
    --     'release-stuck-lifecycle',
    --     '*/5 * * * *',
    --     'SELECT release_stuck_lifecycle_claims(10, 3);'
    --   );
    UPDATE trades
    SET
        lifecycle_status = CASE
            WHEN lifecycle_retry_count + 1 >= max_retry_count
                THEN 'needs_reconciliation'
            ELSE 'idle'
        END,
        lifecycle_worker_id      = NULL,
        lifecycle_claimed_at     = NULL,
        lifecycle_retry_count    = lifecycle_retry_count + 1,
        lifecycle_error = CASE
            WHEN lifecycle_retry_count + 1 >= max_retry_count
                THEN 'Max lifecycle retries reached — manual reconciliation required'
            ELSE lifecycle_error
        END
    WHERE
        status            = 'open'
        AND lifecycle_status IN ('monitoring', 'closing')
        AND lifecycle_claimed_at < NOW() - (max_age_minutes || ' minutes')::INTERVAL;

    GET DIAGNOSTICS affected = ROW_COUNT;
    RETURN affected;
END;
$$;

COMMIT;
