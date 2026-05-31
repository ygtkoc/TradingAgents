-- =============================================================================
-- Migration 0036 - Admin-managed global Trading Brain policies
-- =============================================================================

BEGIN;

DROP POLICY IF EXISTS "knowledge_sources_select" ON public.trading_knowledge_sources;
CREATE POLICY "knowledge_sources_select"
  ON public.trading_knowledge_sources FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR user_id IS NULL OR public.is_admin());

DROP POLICY IF EXISTS "knowledge_sources_insert" ON public.trading_knowledge_sources;
CREATE POLICY "knowledge_sources_insert"
  ON public.trading_knowledge_sources FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid() OR (user_id IS NULL AND public.is_admin()));

DROP POLICY IF EXISTS "knowledge_sources_update" ON public.trading_knowledge_sources;
CREATE POLICY "knowledge_sources_update"
  ON public.trading_knowledge_sources FOR UPDATE TO authenticated
  USING (user_id = auth.uid() OR public.is_admin())
  WITH CHECK (user_id = auth.uid() OR (user_id IS NULL AND public.is_admin()));

DROP POLICY IF EXISTS "knowledge_chunks_select" ON public.trading_knowledge_chunks;
CREATE POLICY "knowledge_chunks_select"
  ON public.trading_knowledge_chunks FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR user_id IS NULL OR public.is_admin());

DROP POLICY IF EXISTS "knowledge_chunks_insert" ON public.trading_knowledge_chunks;
CREATE POLICY "knowledge_chunks_insert"
  ON public.trading_knowledge_chunks FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid() OR (user_id IS NULL AND public.is_admin()));

DROP POLICY IF EXISTS "strategy_rules_select" ON public.trading_strategy_rules;
CREATE POLICY "strategy_rules_select"
  ON public.trading_strategy_rules FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR user_id IS NULL OR public.is_admin());

DROP POLICY IF EXISTS "strategy_rules_insert" ON public.trading_strategy_rules;
CREATE POLICY "strategy_rules_insert"
  ON public.trading_strategy_rules FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid() OR (user_id IS NULL AND public.is_admin()));

DROP POLICY IF EXISTS "strategy_rules_update" ON public.trading_strategy_rules;
CREATE POLICY "strategy_rules_update"
  ON public.trading_strategy_rules FOR UPDATE TO authenticated
  USING (user_id = auth.uid() OR public.is_admin())
  WITH CHECK (user_id = auth.uid() OR (user_id IS NULL AND public.is_admin()));

COMMIT;
