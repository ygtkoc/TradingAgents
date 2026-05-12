-- =============================================================================
-- Migration: 0005_execution_engine.sql
-- Purpose:   Execution Engine support — claiming, trades, trade_events.
--
-- Changes:
--   1. trades table        (created with IF NOT EXISTS for idempotency)
--   2. trade_events table  (immutable audit log of every execution step)
--   3. Execution claiming columns on trade_decisions
--   4. Indexes for fast polling and stuck-execution detection
--   5. release_stuck_executions() function for pg_cron
--
-- Design guarantees:
--   - trade_decisions.execution_status is a TEXT CHECK column (not enum)
--     so adding new states never requires an ALTER TYPE + transaction.
--   - linked_trade_id FK on trade_decisions points to trades, created after
--     trades table exists to avoid circular dependency ordering.
--   - trade_events.trade_id is nullable so events can be written before the
--     trade row exists (e.g., execution_claimed, security_check_failed).
--   - All columns use IF NOT EXISTS / ADD COLUMN IF NOT EXISTS to be
--     safely re-runnable.
-- =============================================================================

BEGIN;

-- ── 1. trades table ────────────────────────────────────────────────────────────
-- The execution engine is the ONLY writer to this table.
-- The agent engine does NOT write here.
CREATE TABLE IF NOT EXISTS trades (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID        NOT NULL,
    bot_id              UUID        NOT NULL,
    trade_decision_id   UUID,                          -- FK added below after trade_decisions patch
    agent_run_id        UUID,
    exchange            TEXT        NOT NULL,
    symbol              TEXT        NOT NULL,
    side                TEXT        NOT NULL
        CONSTRAINT trades_side_check CHECK (side IN ('buy', 'sell')),
    direction           TEXT        NOT NULL
        CONSTRAINT trades_direction_check CHECK (direction IN ('long', 'short', 'neutral')),
    mode                TEXT        NOT NULL
        CONSTRAINT trades_mode_check CHECK (mode IN ('paper', 'live', 'shadow')),
    status              TEXT        NOT NULL DEFAULT 'open'
        CONSTRAINT trades_status_check
            CHECK (status IN ('open', 'closed', 'cancelled', 'failed', 'simulated', 'pending')),
    entry_price         NUMERIC(20,8) NOT NULL,
    quantity            NUMERIC(20,8) NOT NULL,
    stop_loss           NUMERIC(20,8),
    take_profit         NUMERIC(20,8),
    exit_price          NUMERIC(20,8),
    closed_at           TIMESTAMPTZ,
    pnl                 NUMERIC(20,8),
    exchange_order_id   TEXT,
    filled_quantity     NUMERIC(20,8),
    avg_fill_price      NUMERIC(20,8),
    metadata            JSONB       NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE trades IS
    'Live, paper, and shadow trades created exclusively by the Execution Engine.';

COMMENT ON COLUMN trades.trade_decision_id IS
    'The trade_decision that triggered this trade. Used for idempotency checking.';

COMMENT ON COLUMN trades.exchange_order_id IS
    'Exchange-assigned order ID. Null for paper/shadow modes.';

COMMENT ON COLUMN trades.mode IS
    'paper = simulated, no real API call. '
    'shadow = simulated with intended order stored in metadata. '
    'live = real exchange order placed.';

-- ── 2. trade_events table ─────────────────────────────────────────────────────
-- Immutable event log. Rows are NEVER updated or deleted.
-- The execution engine appends events at every step of the execution lifecycle.
CREATE TABLE IF NOT EXISTS trade_events (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    trade_id            UUID        REFERENCES trades(id) ON DELETE RESTRICT,  -- nullable: events before trade creation
    trade_decision_id   UUID,                          -- FK added below
    bot_id              UUID,
    user_id             UUID,
    event_type          TEXT        NOT NULL,
    details             JSONB       NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE trade_events IS
    'Immutable event log for every step of trade execution. Never updated or deleted.';

COMMENT ON COLUMN trade_events.trade_id IS
    'Nullable: events such as execution_claimed, security_check_failed are written '
    'before a trade row exists.';

-- Valid event types (documentation only — enforced in application layer):
--   execution_claimed, risk_check_passed, risk_check_failed,
--   security_check_passed, security_check_failed,
--   paper_trade_opened, shadow_trade_recorded,
--   live_order_submitted, live_order_confirmed, live_order_failed,
--   trade_created, execution_completed, execution_failed, recovery_required

-- ── 3. Execution claiming columns on trade_decisions ──────────────────────────
ALTER TABLE trade_decisions
    ADD COLUMN IF NOT EXISTS execution_status TEXT NOT NULL DEFAULT 'pending_execution'
        CONSTRAINT trade_decisions_execution_status_check
        CHECK (execution_status IN (
            'pending_execution',  -- default: waiting to be picked up
            'executing',          -- claimed by a worker; in progress
            'executed',           -- trade created successfully
            'failed',             -- execution failed; see execution_error
            'skipped'             -- intentionally skipped (risk/security block)
        )),
    ADD COLUMN IF NOT EXISTS execution_worker_id    TEXT        DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS execution_started_at   TIMESTAMPTZ DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS execution_completed_at TIMESTAMPTZ DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS execution_error        TEXT        DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS execution_retry_count  INTEGER     NOT NULL DEFAULT 0,
    -- linked_trade_id is the idempotency anchor: once set, no further execution attempts
    ADD COLUMN IF NOT EXISTS linked_trade_id        UUID        DEFAULT NULL;

-- Add FK from trade_decisions.linked_trade_id → trades.id
-- (trades table already exists from step 1)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_trade_decisions_linked_trade'
    ) THEN
        ALTER TABLE trade_decisions
            ADD CONSTRAINT fk_trade_decisions_linked_trade
            FOREIGN KEY (linked_trade_id)
            REFERENCES trades(id)
            ON DELETE RESTRICT;
    END IF;
END
$$;

-- Add FK from trades.trade_decision_id → trade_decisions.id
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_trades_decision'
    ) THEN
        ALTER TABLE trades
            ADD CONSTRAINT fk_trades_decision
            FOREIGN KEY (trade_decision_id)
            REFERENCES trade_decisions(id)
            ON DELETE RESTRICT;
    END IF;
END
$$;

-- Ensure existing trade_events table from 0001 has trade_decision_id.
-- In 0001, trade_events may already exist without this column, so
-- CREATE TABLE IF NOT EXISTS above will not add it.
ALTER TABLE trade_events
    ADD COLUMN IF NOT EXISTS trade_decision_id UUID DEFAULT NULL;

-- Add FK from trade_events.trade_decision_id → trade_decisions.id
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_trade_events_decision'
    ) THEN
        ALTER TABLE trade_events
            ADD CONSTRAINT fk_trade_events_decision
            FOREIGN KEY (trade_decision_id)
            REFERENCES trade_decisions(id)
            ON DELETE RESTRICT;
    END IF;
END
$$;

COMMENT ON COLUMN trade_decisions.execution_status IS
    'pending_execution → executing → executed | failed | skipped. '
    'Transitions are atomic (UPDATE WHERE execution_status=''pending_execution'' RETURNING *).';

COMMENT ON COLUMN trade_decisions.linked_trade_id IS
    'Set when execution completes. NULL = not yet executed. Used as idempotency anchor.';

COMMENT ON COLUMN trade_decisions.execution_retry_count IS
    'Incremented by release_stuck_executions() when a stale executing row is reset.';

-- ── 4. Indexes ────────────────────────────────────────────────────────────────

-- Fast polling: finds decisions that are ready for execution.
-- The execution engine Phase 1 query hits this index.
CREATE INDEX IF NOT EXISTS idx_trade_decisions_executable
    ON trade_decisions (created_at ASC)
    WHERE final_decision IN ('open_long', 'open_short')
      AND approval_status IN ('approved', 'auto_approved')
      AND execution_status = 'pending_execution'
      AND linked_trade_id IS NULL;

-- Stuck detection: finds decisions that have been 'executing' too long.
CREATE INDEX IF NOT EXISTS idx_trade_decisions_executing_stale
    ON trade_decisions (execution_started_at ASC)
    WHERE execution_status = 'executing';

-- Idempotency lookup: find existing trades for a given decision.
CREATE INDEX IF NOT EXISTS idx_trades_decision_id
    ON trades (trade_decision_id)
    WHERE trade_decision_id IS NOT NULL;

-- Trade events lookup per decision (for event log retrieval).
CREATE INDEX IF NOT EXISTS idx_trade_events_decision
    ON trade_events (trade_decision_id, created_at ASC)
    WHERE trade_decision_id IS NOT NULL;

-- Trade events lookup per trade.
CREATE INDEX IF NOT EXISTS idx_trade_events_trade
    ON trade_events (trade_id, created_at ASC)
    WHERE trade_id IS NOT NULL;

-- ── 5. release_stuck_executions() function ────────────────────────────────────
-- Call via pg_cron every 5 minutes.
-- Resets decisions stuck in 'executing' back to 'pending_execution'.
-- After MAX_RETRIES (default 3) attempts, marks as 'failed'.
CREATE OR REPLACE FUNCTION release_stuck_executions(
    max_age_minutes     INT     DEFAULT 10,
    max_retry_count     INT     DEFAULT 3
)
RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    released INT := 0;
    failed   INT := 0;
BEGIN
    -- Decisions that have been 'executing' too long AND have retries remaining
    -- → reset to pending_execution for retry
    UPDATE trade_decisions
    SET
        execution_status       = 'pending_execution',
        execution_worker_id    = NULL,
        execution_started_at   = NULL,
        execution_retry_count  = execution_retry_count + 1
    WHERE
        execution_status = 'executing'
        AND execution_started_at < NOW() - (max_age_minutes * INTERVAL '1 minute')
        AND execution_retry_count < max_retry_count;

    GET DIAGNOSTICS released = ROW_COUNT;

    -- Decisions that have exhausted all retries → mark as failed permanently
    UPDATE trade_decisions
    SET
        execution_status       = 'failed',
        execution_worker_id    = NULL,
        execution_error        = 'Max retry count exceeded; marked failed by release_stuck_executions()',
        execution_completed_at = NOW()
    WHERE
        execution_status = 'executing'
        AND execution_started_at < NOW() - (max_age_minutes * INTERVAL '1 minute')
        AND execution_retry_count >= max_retry_count;

    GET DIAGNOSTICS failed = ROW_COUNT;

    IF released > 0 OR failed > 0 THEN
        RAISE NOTICE 'release_stuck_executions: released=%, failed=%', released, failed;
    END IF;

    RETURN released + failed;
END;
$$;

COMMENT ON FUNCTION release_stuck_executions IS
    'Resets stale executing decisions. Call via pg_cron every 5 minutes: '
    'SELECT cron.schedule(''release-stuck-executions'', ''*/5 * * * *'', '
    '$$SELECT release_stuck_executions(10, 3)$$)';

-- Enable pg_cron (uncomment after enabling the extension):
-- SELECT cron.schedule(
--     'release-stuck-executions',
--     '*/5 * * * *',
--     $$SELECT release_stuck_executions(10, 3)$$
-- );

-- ── 6. RLS: execution engine uses service_role; no RLS restrictions ────────────
-- The execution engine always uses the service_role key, which bypasses RLS.
-- No additional RLS policies are needed for the execution engine.
-- Frontend/users CANNOT write to trades or trade_events directly (enforced by
-- migration 0003_lock_core_pipeline_writes.sql which revokes INSERT/UPDATE/DELETE
-- on core tables from the authenticated role).

-- ── 7. Verification ───────────────────────────────────────────────────────────
-- Run after applying to verify:
--
-- -- Check new columns on trade_decisions:
-- SELECT column_name, data_type, column_default
-- FROM information_schema.columns
-- WHERE table_name = 'trade_decisions'
--   AND column_name IN (
--     'execution_status', 'execution_worker_id', 'execution_started_at',
--     'execution_completed_at', 'execution_error', 'execution_retry_count',
--     'linked_trade_id'
--   );
-- Expected: 7 rows
--
-- -- Check trades and trade_events tables exist:
-- SELECT table_name FROM information_schema.tables
-- WHERE table_name IN ('trades', 'trade_events');
-- Expected: 2 rows
--
-- -- Check indexes:
-- SELECT indexname FROM pg_indexes
-- WHERE tablename IN ('trade_decisions', 'trades', 'trade_events')
--   AND indexname LIKE 'idx_%';

COMMIT;
