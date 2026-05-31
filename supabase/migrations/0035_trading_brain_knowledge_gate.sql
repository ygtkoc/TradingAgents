-- =============================================================================
-- Migration 0035 - Trading Brain knowledge library and gate reviews
-- =============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS public.trading_knowledge_sources (
  id           uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id      uuid REFERENCES public.profiles(id) ON DELETE CASCADE,
  title        text NOT NULL,
  source_type  text NOT NULL DEFAULT 'note'
    CHECK (source_type IN ('note','article','video_transcript','pdf','strategy','post_trade')),
  content_text text NOT NULL,
  status       text NOT NULL DEFAULT 'active'
    CHECK (status IN ('active','archived')),
  metadata     jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.trading_knowledge_chunks (
  id         uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  source_id  uuid NOT NULL REFERENCES public.trading_knowledge_sources(id) ON DELETE CASCADE,
  user_id    uuid REFERENCES public.profiles(id) ON DELETE CASCADE,
  chunk_index integer NOT NULL DEFAULT 0,
  content    text NOT NULL,
  tags       text[] NOT NULL DEFAULT '{}',
  metadata   jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.trading_strategy_rules (
  id          uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id     uuid REFERENCES public.profiles(id) ON DELETE CASCADE,
  source_id   uuid REFERENCES public.trading_knowledge_sources(id) ON DELETE SET NULL,
  rule_code   text NOT NULL,
  title       text NOT NULL,
  rule_text   text NOT NULL,
  category    text NOT NULL DEFAULT 'general',
  severity    text NOT NULL DEFAULT 'medium'
    CHECK (severity IN ('low','medium','high','critical')),
  weight      integer NOT NULL DEFAULT 10,
  active      boolean NOT NULL DEFAULT true,
  metadata    jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.decision_knowledge_reviews (
  id                  uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  trade_decision_id   uuid NOT NULL REFERENCES public.trade_decisions(id) ON DELETE CASCADE,
  user_id             uuid REFERENCES public.profiles(id) ON DELETE CASCADE,
  knowledge_score     integer NOT NULL DEFAULT 0,
  verdict             text NOT NULL DEFAULT 'review'
    CHECK (verdict IN ('pass','review','block')),
  supporting_rules    jsonb NOT NULL DEFAULT '[]'::jsonb,
  violated_rules      jsonb NOT NULL DEFAULT '[]'::jsonb,
  retrieved_chunks    jsonb NOT NULL DEFAULT '[]'::jsonb,
  critic_summary      text NOT NULL DEFAULT '',
  visual_annotations  jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at          timestamptz NOT NULL DEFAULT now(),
  UNIQUE (trade_decision_id)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_sources_user ON public.trading_knowledge_sources(user_id, status);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_user_tags ON public.trading_knowledge_chunks USING gin(tags);
CREATE INDEX IF NOT EXISTS idx_strategy_rules_user_active ON public.trading_strategy_rules(user_id, active);
CREATE INDEX IF NOT EXISTS idx_decision_knowledge_reviews_decision ON public.decision_knowledge_reviews(trade_decision_id);

CREATE TRIGGER trading_knowledge_sources_updated_at
  BEFORE UPDATE ON public.trading_knowledge_sources
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trading_strategy_rules_updated_at
  BEFORE UPDATE ON public.trading_strategy_rules
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.trading_knowledge_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trading_knowledge_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trading_strategy_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.decision_knowledge_reviews ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "knowledge_sources_select" ON public.trading_knowledge_sources;
CREATE POLICY "knowledge_sources_select"
  ON public.trading_knowledge_sources FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR user_id IS NULL);

DROP POLICY IF EXISTS "knowledge_sources_insert" ON public.trading_knowledge_sources;
CREATE POLICY "knowledge_sources_insert"
  ON public.trading_knowledge_sources FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid());

DROP POLICY IF EXISTS "knowledge_sources_update" ON public.trading_knowledge_sources;
CREATE POLICY "knowledge_sources_update"
  ON public.trading_knowledge_sources FOR UPDATE TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

DROP POLICY IF EXISTS "knowledge_chunks_select" ON public.trading_knowledge_chunks;
CREATE POLICY "knowledge_chunks_select"
  ON public.trading_knowledge_chunks FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR user_id IS NULL);

DROP POLICY IF EXISTS "knowledge_chunks_insert" ON public.trading_knowledge_chunks;
CREATE POLICY "knowledge_chunks_insert"
  ON public.trading_knowledge_chunks FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid());

DROP POLICY IF EXISTS "strategy_rules_select" ON public.trading_strategy_rules;
CREATE POLICY "strategy_rules_select"
  ON public.trading_strategy_rules FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR user_id IS NULL);

DROP POLICY IF EXISTS "strategy_rules_insert" ON public.trading_strategy_rules;
CREATE POLICY "strategy_rules_insert"
  ON public.trading_strategy_rules FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid());

DROP POLICY IF EXISTS "strategy_rules_update" ON public.trading_strategy_rules;
CREATE POLICY "strategy_rules_update"
  ON public.trading_strategy_rules FOR UPDATE TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

DROP POLICY IF EXISTS "knowledge_reviews_select" ON public.decision_knowledge_reviews;
CREATE POLICY "knowledge_reviews_select"
  ON public.decision_knowledge_reviews FOR SELECT TO authenticated
  USING (user_id = auth.uid());

INSERT INTO public.trading_strategy_rules
  (user_id, rule_code, title, rule_text, category, severity, weight, metadata)
VALUES
  (NULL, 'stop_required', 'Stop is required', 'Every trade must have a defined invalidation/stop level before execution.', 'risk', 'critical', 30, '{"system":true}'::jsonb),
  (NULL, 'minimum_rr', 'Minimum reward/risk', 'Trades should have at least 1.5R planned reward before execution.', 'risk', 'high', 20, '{"min_rr":1.5,"system":true}'::jsonb),
  (NULL, 'no_duplicate_exposure', 'No duplicate symbol exposure', 'Do not open a new trade while the same symbol already has an open position.', 'risk', 'critical', 25, '{"system":true}'::jsonb),
  (NULL, 'avoid_fomo_chase', 'Avoid late chase', 'Avoid opening fresh trades after an extended move unless invalidation is tight and structure is clear.', 'psychology', 'medium', 10, '{"system":true}'::jsonb),
  (NULL, 'visual_explanation_required', 'Visual reasoning required', 'A decision should record entry, stop, TP, support/resistance and trend rationale so the operator can inspect it visually.', 'documentation', 'medium', 10, '{"system":true}'::jsonb)
ON CONFLICT DO NOTHING;

GRANT SELECT, INSERT, UPDATE ON public.trading_knowledge_sources TO authenticated;
GRANT SELECT, INSERT ON public.trading_knowledge_chunks TO authenticated;
GRANT SELECT, INSERT, UPDATE ON public.trading_strategy_rules TO authenticated;
GRANT SELECT ON public.decision_knowledge_reviews TO authenticated;

COMMIT;
