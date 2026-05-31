-- =============================================================================
-- Migration 0040 - Grant service_role access to Trading Brain tables
-- =============================================================================

BEGIN;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.trading_knowledge_sources TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.trading_knowledge_chunks TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.trading_strategy_rules TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.decision_knowledge_reviews TO service_role;

COMMIT;
