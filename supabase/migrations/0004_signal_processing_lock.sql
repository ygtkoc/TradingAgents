-- =============================================================================
-- Migration: 0004_signal_processing_lock_fixed.sql
-- Purpose:   Adds optimistic concurrency locking columns to the signals table.
--
-- FIXED VERSION:
--   PostgreSQL does not allow a newly added enum value to be used as an enum
--   literal inside the same transaction. The original migration failed with:
--     unsafe use of new value "processing" of enum type signal_status
--
--   This version avoids that issue by:
--     1. Adding the enum value if missing.
--     2. Avoiding direct enum literal usage for the new value in index/function
--        predicates inside the migration.
--
-- After this migration commits, application code can safely use:
--   status = 'processing'
-- =============================================================================

-- ── 1. Add 'processing' to signal_status enum ─────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_enum
        WHERE enumlabel = 'processing'
          AND enumtypid = (
              SELECT oid FROM pg_type WHERE typname = 'signal_status'
          )
    ) THEN
        ALTER TYPE public.signal_status ADD VALUE 'processing' AFTER 'pending';
    END IF;
END
$$;

-- ── 2. Add processing lock columns ────────────────────────────────────────────
ALTER TABLE public.signals
    ADD COLUMN IF NOT EXISTS processing_worker_id   TEXT        DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS processing_started_at  TIMESTAMPTZ DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS retry_count            INT         DEFAULT 0;

-- processed_at already exists in 0001_initial_schema.sql, but keep this harmless
-- for compatibility in case an older 0001 is used.
ALTER TABLE public.signals
    ADD COLUMN IF NOT EXISTS processed_at TIMESTAMPTZ DEFAULT NULL;

COMMENT ON COLUMN public.signals.processing_worker_id IS
    'Worker ID that has claimed this signal for processing. NULL = unclaimed.';

COMMENT ON COLUMN public.signals.processing_started_at IS
    'Timestamp when the worker claimed this signal. Used for stuck-signal detection.';

COMMENT ON COLUMN public.signals.processed_at IS
    'Timestamp when the signal was successfully processed. Set by mark_processed().';

COMMENT ON COLUMN public.signals.retry_count IS
    'Number of times this signal has been released from stuck processing state. Incremented by release_stuck_signals().';

-- ── 3. Partial index: fast polling for pending, unclaimed signals ──────────────
-- pending already existed before this migration, so direct enum literal usage is safe.
CREATE INDEX IF NOT EXISTS idx_signals_pending_unclaimed
    ON public.signals (created_at ASC)
    WHERE status = 'pending' AND processing_worker_id IS NULL;

-- ── 4. Index: find stuck processing signals ───────────────────────────────────
-- Do NOT use WHERE status = 'processing' here because the enum value may be new
-- in this same migration transaction. This index still supports stuck-signal scans.
CREATE INDEX IF NOT EXISTS idx_signals_stuck_processing
    ON public.signals (processing_started_at ASC)
    WHERE processing_worker_id IS NOT NULL
      AND processing_started_at IS NOT NULL;

-- ── 5. Function: release stuck signals ────────────────────────────────────────
-- Uses status::text = 'processing' to avoid unsafe enum literal usage in this
-- same migration transaction.
CREATE OR REPLACE FUNCTION public.release_stuck_signals(timeout_minutes INT DEFAULT 5)
RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    released INT;
BEGIN
    UPDATE public.signals
    SET
        status                 = 'pending',
        processing_worker_id   = NULL,
        processing_started_at  = NULL,
        retry_count            = COALESCE(retry_count, 0) + 1
    WHERE
        status::text = 'processing'
        AND processing_started_at < NOW() - (timeout_minutes * INTERVAL '1 minute');

    GET DIAGNOSTICS released = ROW_COUNT;

    IF released > 0 THEN
        RAISE NOTICE 'release_stuck_signals: released % stuck signals', released;
    END IF;

    RETURN released;
END;
$$;

COMMENT ON FUNCTION public.release_stuck_signals(INT) IS
    'Releases signals stuck in processing state. Call via pg_cron every 5 minutes: SELECT release_stuck_signals(5).';

-- ── 6. Optional pg_cron registration ──────────────────────────────────────────
-- To enable later after pg_cron is configured, run manually:
--
-- SELECT cron.schedule(
--     'release-stuck-signals',
--     '*/5 * * * *',
--     $$SELECT public.release_stuck_signals(5)$$
-- );

-- ── 7. Verification query ─────────────────────────────────────────────────────
-- SELECT column_name, data_type, column_default, is_nullable
-- FROM information_schema.columns
-- WHERE table_schema = 'public'
--   AND table_name = 'signals'
--   AND column_name IN (
--       'processing_worker_id', 'processing_started_at',
--       'processed_at', 'retry_count'
--   );
--
-- SELECT enumlabel FROM pg_enum
-- WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'signal_status')
-- ORDER BY enumsortorder;
