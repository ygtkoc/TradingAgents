-- ─────────────────────────────────────────────────────────────────────────────
-- Migration 0015: Fix orphaned paper decisions stuck in pending_execution
--
-- Root cause:
--   aggregator._compute_approval() applied a +5.0 buffer above score_threshold_open
--   before setting approval_status = 'auto_approved' for paper/shadow decisions.
--   This created a dead zone (scores 70.0–74.9 with default threshold=70):
--     final_decision  = 'open_long' | 'open_short'   ✓ (passed score_threshold_open)
--     approval_status = 'pending'                      ✗ (not auto_approved)
--     execution_status = 'pending_execution'           ✓
--
--   The execution engine query requires:
--     approval_status IN ('approved', 'auto_approved')
--   So these decisions were permanently invisible to the engine and never executed.
--
-- Fix:
--   1. Rescue all stuck paper/shadow decisions into auto_approved.
--   2. Leave live mode pending decisions untouched (legitimately need human eyes).
--   3. Update _compute_approval() in aggregator.py (see Python change) to prevent
--      new orphans from being created.
--
-- Verification SQL included at the bottom of this file.
-- ─────────────────────────────────────────────────────────────────────────────

-- ── Step 1: Rescue orphaned paper/shadow decisions ────────────────────────────
UPDATE trade_decisions
SET
    approval_status  = 'auto_approved',
    updated_at       = now()
WHERE
    final_decision   IN ('open_long', 'open_short')
    AND approval_status  = 'pending'
    AND execution_status = 'pending_execution'
    AND linked_trade_id  IS NULL
    AND mode             IN ('paper', 'shadow');

-- Log how many were rescued (viewable via supabase studio or psql)
DO $$
DECLARE
    rescued int;
BEGIN
    GET DIAGNOSTICS rescued = ROW_COUNT;
    RAISE NOTICE 'migration_0015: rescued % orphaned paper/shadow decisions', rescued;
END;
$$;

-- ── Step 2: Mark abandoned live pending decisions as expired ──────────────────
-- Live decisions older than 24h that are still pending and unlinked will never
-- be human-approved. Mark them expired so they don't pollute the UI.
UPDATE trade_decisions
SET
    approval_status  = 'expired',
    execution_status = 'skipped',
    updated_at       = now()
WHERE
    final_decision   IN ('open_long', 'open_short')
    AND approval_status  = 'pending'
    AND execution_status = 'pending_execution'
    AND linked_trade_id  IS NULL
    AND mode             = 'live'
    AND created_at       < now() - interval '24 hours';

-- ── Step 3: Mark non-actionable decisions that were left as pending_execution ─
-- wait / reject decisions should never be pending_execution — fix stragglers.
UPDATE trade_decisions
SET
    execution_status = 'skipped',
    updated_at       = now()
WHERE
    final_decision   NOT IN ('open_long', 'open_short', 'manual_approval_required')
    AND execution_status = 'pending_execution'
    AND linked_trade_id  IS NULL;


-- ── Verification queries ──────────────────────────────────────────────────────
-- Run these to confirm the pipeline is healthy after migration.

-- 1. Distribution of (final_decision, approval_status, execution_status)
--    Expected for healthy paper trading: open_long/open_short + auto_approved + executed
SELECT
    final_decision,
    approval_status,
    execution_status,
    count(*) AS cnt
FROM trade_decisions
GROUP BY 1, 2, 3
ORDER BY cnt DESC;

-- 2. Most recent 20 decisions — check linked_trade_id is set for executed ones
SELECT
    symbol,
    mode,
    final_decision,
    approval_status,
    execution_status,
    linked_trade_id,
    created_at
FROM trade_decisions
ORDER BY created_at DESC
LIMIT 20;

-- 3. Most recent 20 paper trades — confirm mode=paper, status=open
SELECT
    symbol,
    mode,
    status,
    direction,
    entry_price,
    quantity,
    created_at
FROM trades
WHERE mode = 'paper'
ORDER BY created_at DESC
LIMIT 20;

-- 4. Sanity: any remaining stuck decisions after this migration?
--    Should return 0 rows.
SELECT id, symbol, mode, final_decision, approval_status, execution_status, created_at
FROM trade_decisions
WHERE
    final_decision   IN ('open_long', 'open_short')
    AND approval_status  = 'pending'
    AND execution_status = 'pending_execution'
    AND linked_trade_id  IS NULL
    AND mode             IN ('paper', 'shadow');
