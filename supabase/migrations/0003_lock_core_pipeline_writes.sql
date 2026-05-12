-- ============================================================
-- TradingAgents Platform — Security Patch: Lock Core Pipeline Writes
-- Migration: 0003_lock_core_pipeline_writes.sql
-- Depends on: 0001_initial_schema.sql
--
-- PROBLEM FIXED:
--   0001 granted authenticated users INSERT/UPDATE on agent_runs,
--   agent_outputs, trade_decisions, trades, trade_events, risk_logs,
--   and signals. Any authenticated user could therefore:
--     - Fabricate agent runs and outputs, bypassing the AI pipeline
--     - Create fake trade decisions with forged risk/security summaries
--     - Insert fake trades with fabricated PnL and execution status
--     - Write false risk log entries to suppress real risk events
--     - Emit false trade events to corrupt audit trails
--     - Inject rogue signals to trigger unintended bot execution
--
-- SECURITY MODEL AFTER THIS MIGRATION:
--   - authenticated role: SELECT own rows only on all pipeline tables
--   - service_role (Edge Functions, Python Agent Engine): full write access
--     via RLS bypass — no policies needed, no grants needed
--   - admin/super_admin: SELECT all rows for support access only;
--     any admin mutation must occur via Edge Functions with explicit
--     audit logging, not via direct table access
--
-- TABLES AFFECTED:
--   agent_runs, agent_outputs, signals, trade_decisions, trades,
--   trade_events, risk_logs
-- ============================================================

BEGIN;

-- ============================================================
-- STEP 1: DROP UNSAFE INSERT / UPDATE POLICIES
-- ============================================================

-- ── agent_runs ───────────────────────────────────────────────
-- Was: authenticated users could insert/update their own agent runs.
-- After: only service_role writes. Fabricating an agent run to skip
-- the AI pipeline or alter run_status/input_snapshot is now impossible
-- via the client API.
DROP POLICY IF EXISTS "agent_runs_insert" ON public.agent_runs;
DROP POLICY IF EXISTS "agent_runs_update" ON public.agent_runs;

-- ── agent_outputs ─────────────────────────────────────────────
-- Was: authenticated users could insert agent outputs attributed to themselves.
-- After: only service_role writes. Users cannot forge agent decisions,
-- confidence scores, veto flags, or reasoning text.
DROP POLICY IF EXISTS "agent_outputs_insert" ON public.agent_outputs;

-- ── signals ──────────────────────────────────────────────────
-- Was: authenticated users could insert and update signals, including
-- setting direction, confidence, and status directly.
-- After: only service_role writes. See STEP 4 for manual signal path.
DROP POLICY IF EXISTS "signals_insert" ON public.signals;
DROP POLICY IF EXISTS "signals_update" ON public.signals;

-- ── trade_decisions ───────────────────────────────────────────
-- Was: authenticated users could insert decisions or alter approval_status,
-- final_decision, score_summary, veto_summary, and agent_outputs_snapshot.
-- After: only service_role writes. Manual approval now flows exclusively
-- through a dedicated Edge Function (see STEP 4).
DROP POLICY IF EXISTS "trade_decisions_insert" ON public.trade_decisions;
DROP POLICY IF EXISTS "trade_decisions_update" ON public.trade_decisions;

-- ── trades ───────────────────────────────────────────────────
-- Was: authenticated users could insert trades and update status, PnL,
-- exit_price, realized_pnl, exchange_order_id, and mode.
-- After: only service_role writes. Fabricating trade records or inflating
-- PnL figures is now structurally impossible via the client API.
DROP POLICY IF EXISTS "trades_insert" ON public.trades;
DROP POLICY IF EXISTS "trades_update" ON public.trades;

-- ── trade_events ─────────────────────────────────────────────
-- Was: authenticated users could append arbitrary event records to any
-- trade they owned, allowing audit trail pollution.
-- After: only service_role writes. The event log is now immutable from
-- the client's perspective. See STEP 4 for user-note path if needed.
DROP POLICY IF EXISTS "trade_events_insert" ON public.trade_events;

-- ── risk_logs ────────────────────────────────────────────────
-- Was: authenticated users could insert risk log entries, allowing them
-- to suppress real risk events by flooding the log or forge "resolved"
-- entries (note: resolved UPDATE was already absent, but INSERT was open).
-- After: only service_role writes.
DROP POLICY IF EXISTS "risk_logs_insert" ON public.risk_logs;

-- ============================================================
-- STEP 2: REVOKE WRITE GRANTS FROM authenticated ROLE
--
-- Dropping RLS policies is necessary but not sufficient.
-- Revoking the table-level privilege adds a second independent
-- enforcement layer. A future accidental policy re-addition cannot
-- re-enable writes unless the GRANT is also restored.
-- ============================================================

-- agent_runs: SELECT only
REVOKE INSERT, UPDATE ON public.agent_runs      FROM authenticated;

-- agent_outputs: SELECT only
REVOKE INSERT         ON public.agent_outputs   FROM authenticated;

-- signals: SELECT only
REVOKE INSERT, UPDATE ON public.signals         FROM authenticated;

-- trade_decisions: SELECT only
REVOKE INSERT, UPDATE ON public.trade_decisions FROM authenticated;

-- trades: SELECT only
REVOKE INSERT, UPDATE ON public.trades          FROM authenticated;

-- trade_events: SELECT only (system-generated events only)
REVOKE INSERT         ON public.trade_events    FROM authenticated;

-- risk_logs: SELECT only
REVOKE INSERT         ON public.risk_logs       FROM authenticated;

-- ============================================================
-- STEP 3: VERIFY SELECT POLICIES REMAIN CORRECT
--
-- The SELECT policies from 0001 are already safe and remain unchanged:
--   agent_runs_select    : user_id = auth.uid() OR is_admin()
--   agent_outputs_select : user_id = auth.uid() OR is_admin()
--   signals_select       : user_id = auth.uid() OR is_admin()
--   trade_decisions_select: user_id = auth.uid() OR is_admin()
--   trades_select        : user_id = auth.uid() OR is_admin()
--   trade_events_select  : user_id = auth.uid() OR is_admin()
--   risk_logs_select     : user_id = auth.uid() OR is_admin()
--
-- No action needed. This comment block is an explicit audit record
-- that the SELECT side was reviewed and intentionally left in place.
-- ============================================================

-- ============================================================
-- STEP 4: CONTROLLED WRITE PATHS FOR FUTURE EDGE FUNCTIONS
--
-- The following trusted write paths MUST be implemented as Edge
-- Functions using the service_role key. Each is documented here
-- so the Edge Function layer is built with full awareness of what
-- was previously exposed and is now locked.
--
-- [EF-01] POST /agent-engine/run
--   Creates: agent_runs, agent_outputs, trade_decisions (via service_role)
--   Called by: Python Agent Engine only
--   Auth: service_role header secret, not user JWT
--
-- [EF-02] POST /trade/approve  (manual approval)
--   Updates: trade_decisions.approval_status, approved_by, approved_at
--   Called by: authenticated user who owns the decision
--   Validation: decision must have manual_approval_required=true AND
--               approval_status='pending' AND belong to auth.uid()
--   Audit: must INSERT into audit_logs before UPDATE
--   Uses: service_role to perform the targeted UPDATE
--
-- [EF-03] POST /trade/execute  (execution agent)
--   Creates: trades row, initial trade_events row
--   Called by: Python Execution Agent only (service_role)
--   Validation: trade_decision must have approval_status IN ('approved','auto_approved')
--
-- [EF-04] POST /signals/manual  (user-initiated signal, if supported)
--   Creates: signals row with signal_type='manual', status='pending'
--   Called by: authenticated user
--   Validation: bot must belong to user; bot.mode must be 'paper' unless
--               subscription.real_trading_allowed = true
--   Note: The signal is created but still flows through the full agent
--         pipeline before becoming a trade_decision. Users cannot
--         shortcut the pipeline — they can only trigger its input.
--   Uses: service_role for the INSERT after server-side validation
--
-- [EF-05] POST /trade/event/note  (optional user annotation)
--   Creates: trade_events row with event_type='user_note', source='user'
--   Called by: authenticated user who owns the trade
--   Validation: trade must belong to user; no system field mutation
--   Uses: service_role for the INSERT
--   Rationale: Keeps the trade_events append-only invariant while
--              allowing user-added notes. Event_type='user_note' allows
--              the frontend and agents to filter out user annotations.
-- ============================================================

-- ============================================================
-- STEP 5: ANNOTATE TABLES WITH SECURITY COMMENTS
-- ============================================================

COMMENT ON TABLE public.agent_runs IS
  'WRITE: service_role only (Python Agent Engine via [EF-01]). '
  'READ: authenticated users see own rows; admins see all. '
  'Never expose INSERT/UPDATE to authenticated role.';

COMMENT ON TABLE public.agent_outputs IS
  'WRITE: service_role only (Python Agent Engine via [EF-01]). '
  'READ: authenticated users see own rows; admins see all. '
  'Immutable once written — no UPDATE policy exists or should exist.';

COMMENT ON TABLE public.signals IS
  'WRITE: service_role only. User-triggered signals use [EF-04] '
  'which validates and inserts via service_role. '
  'READ: authenticated users see own rows; admins see all.';

COMMENT ON TABLE public.trade_decisions IS
  'WRITE: service_role only (agent engine [EF-01]). '
  'Manual approval exclusively via [EF-02] Edge Function which '
  'audits the action before performing a targeted service_role UPDATE. '
  'READ: authenticated users see own rows; admins see all.';

COMMENT ON TABLE public.trades IS
  'WRITE: service_role only (execution agent [EF-03]). '
  'PnL, status, and execution fields may only be updated by trusted '
  'backend services. Fabricating trades via client API is structurally blocked. '
  'READ: authenticated users see own rows; admins see all.';

COMMENT ON TABLE public.trade_events IS
  'WRITE: service_role only for system events. '
  'User annotations use [EF-05] with event_type=''user_note''. '
  'Append-only — no UPDATE or DELETE policy exists. '
  'READ: authenticated users see own rows; admins see all.';

COMMENT ON TABLE public.risk_logs IS
  'WRITE: service_role only (risk engine and agent pipeline). '
  'Users cannot suppress, forge, or modify risk events. '
  'READ: authenticated users see own rows; admins see all.';

-- ============================================================
-- STEP 6: IDEMPOTENCY GUARD
--
-- These tables must never have INSERT/UPDATE policies for the
-- authenticated role. This block documents the invariant so that
-- future migrations can be checked against it.
--
-- To verify in psql or Supabase SQL editor:
--
--   SELECT tablename, policyname, cmd
--   FROM pg_policies
--   WHERE schemaname = 'public'
--     AND tablename IN (
--       'agent_runs','agent_outputs','signals',
--       'trade_decisions','trades','trade_events','risk_logs'
--     )
--     AND cmd IN ('INSERT','UPDATE','ALL')
--     AND roles @> ARRAY['authenticated']::name[];
--
-- Expected result: 0 rows.
-- Any row returned means a policy was re-added and must be reviewed.
-- ============================================================

COMMIT;
