-- =============================================================================
-- Migration 0037 - Seed crypto trading knowledge sample
-- =============================================================================

BEGIN;

WITH payload AS (
  SELECT * FROM jsonb_to_recordset($json$
  [
    {
      "title": "Bull Flag Pattern",
      "source_type": "strategy",
      "content_text": "Bull Flag is a continuation pattern formed after a strong impulsive move. Entry occurs on breakout above the flag resistance with increasing volume. Stop loss below flag low. Target measured from the flagpole length.",
      "metadata": { "category": "chart_pattern", "tags": ["bull_flag", "continuation", "breakout"], "priority": "high", "evidence_level": "education" }
    },
    {
      "title": "Bear Flag Pattern",
      "source_type": "strategy",
      "content_text": "Bear Flag appears after a strong bearish move followed by a weak upward retracement. Entry occurs when price breaks below support. Volume expansion confirms continuation.",
      "metadata": { "category": "chart_pattern", "tags": ["bear_flag", "continuation", "breakdown"], "priority": "high", "evidence_level": "education" }
    },
    {
      "title": "Double Top Reversal",
      "source_type": "strategy",
      "content_text": "Double Top forms when price fails twice at the same resistance level. Confirmation occurs when neckline support breaks. Target equals pattern height.",
      "metadata": { "category": "chart_pattern", "tags": ["double_top", "reversal", "bearish"], "priority": "high", "evidence_level": "education" }
    },
    {
      "title": "Double Bottom Reversal",
      "source_type": "strategy",
      "content_text": "Double Bottom forms when price rejects a support level twice. Confirmation occurs after neckline breakout. Increased volume strengthens validity.",
      "metadata": { "category": "chart_pattern", "tags": ["double_bottom", "reversal", "bullish"], "priority": "high", "evidence_level": "education" }
    },
    {
      "title": "Head And Shoulders",
      "source_type": "strategy",
      "content_text": "Head and Shoulders is a bearish reversal pattern consisting of left shoulder, head, and right shoulder. A neckline breakdown confirms trend reversal.",
      "metadata": { "category": "chart_pattern", "tags": ["head_shoulders", "reversal", "bearish"], "priority": "high", "evidence_level": "education" }
    },
    {
      "title": "Inverse Head And Shoulders",
      "source_type": "strategy",
      "content_text": "Inverse Head and Shoulders is a bullish reversal pattern. Entry occurs after neckline breakout and retest confirmation.",
      "metadata": { "category": "chart_pattern", "tags": ["inverse_hs", "bullish", "reversal"], "priority": "high", "evidence_level": "education" }
    },
    {
      "title": "Ascending Triangle",
      "source_type": "strategy",
      "content_text": "Ascending Triangle consists of higher lows beneath horizontal resistance. Breakout probability increases as compression develops.",
      "metadata": { "category": "chart_pattern", "tags": ["ascending_triangle", "breakout", "bullish"], "priority": "high", "evidence_level": "education" }
    },
    {
      "title": "Descending Triangle",
      "source_type": "strategy",
      "content_text": "Descending Triangle consists of lower highs pressing into support. Breakdown often results in continuation of bearish trend.",
      "metadata": { "category": "chart_pattern", "tags": ["descending_triangle", "bearish", "breakdown"], "priority": "high", "evidence_level": "education" }
    },
    {
      "title": "Fair Value Gap",
      "source_type": "strategy",
      "content_text": "Fair Value Gap represents an inefficiency created by an impulsive move. Markets frequently retrace into the gap before continuing trend direction.",
      "metadata": { "category": "ict", "tags": ["fvg", "imbalance", "ict"], "priority": "high", "evidence_level": "education" }
    },
    {
      "title": "Order Block",
      "source_type": "strategy",
      "content_text": "An Order Block is the final opposing candle before a strong displacement move. Institutions are believed to leave unfilled orders in these zones.",
      "metadata": { "category": "smart_money", "tags": ["order_block", "smc", "institutional"], "priority": "high", "evidence_level": "education" }
    },
    {
      "title": "Liquidity Sweep",
      "source_type": "strategy",
      "content_text": "Liquidity Sweep occurs when price takes previous highs or lows before reversing. Sweeps often trigger stop losses and provide liquidity for large participants.",
      "metadata": { "category": "smart_money", "tags": ["liquidity", "stop_hunt", "smc"], "priority": "high", "evidence_level": "education" }
    },
    {
      "title": "Break Of Structure",
      "source_type": "strategy",
      "content_text": "Break Of Structure confirms a shift in market direction when a significant swing high or swing low is violated.",
      "metadata": { "category": "market_structure", "tags": ["bos", "trend_change", "smc"], "priority": "high", "evidence_level": "education" }
    },
    {
      "title": "Change Of Character",
      "source_type": "strategy",
      "content_text": "CHOCH is an early signal of market structure transition and may appear before a complete trend reversal develops.",
      "metadata": { "category": "market_structure", "tags": ["choch", "trend_shift", "smc"], "priority": "high", "evidence_level": "education" }
    },
    {
      "title": "RSI Divergence",
      "source_type": "strategy",
      "content_text": "Bullish divergence occurs when price makes lower lows while RSI makes higher lows. Bearish divergence occurs in the opposite condition.",
      "metadata": { "category": "indicator", "tags": ["rsi", "divergence", "momentum"], "priority": "medium", "evidence_level": "education" }
    },
    {
      "title": "ADX Trend Strength",
      "source_type": "strategy",
      "content_text": "ADX above 25 suggests trend strength. ADX below 20 often indicates range-bound conditions and lower trend persistence.",
      "metadata": { "category": "indicator", "tags": ["adx", "trend", "strength"], "priority": "medium", "evidence_level": "education" }
    },
    {
      "title": "Risk Per Trade Rule",
      "source_type": "note",
      "content_text": "Never risk more than 1% of total account equity on a single trade. Survival precedes profitability.",
      "metadata": { "category": "risk_management", "tags": ["risk", "position_sizing", "capital_preservation"], "priority": "critical", "evidence_level": "education" }
    },
    {
      "title": "Maximum Daily Drawdown",
      "source_type": "note",
      "content_text": "If daily account drawdown exceeds 3%, trading activity should stop for the remainder of the session.",
      "metadata": { "category": "risk_management", "tags": ["drawdown", "discipline", "risk"], "priority": "critical", "evidence_level": "education" }
    },
    {
      "title": "Trading In The Zone Principle",
      "source_type": "article",
      "content_text": "Every trade is unique. Traders should think in probabilities and avoid emotional attachment to individual outcomes.",
      "metadata": { "category": "psychology", "tags": ["mindset", "probability", "mark_douglas"], "priority": "high", "evidence_level": "education" }
    },
    {
      "title": "News Event Protection",
      "source_type": "note",
      "content_text": "Avoid opening new positions within 60 minutes before major economic releases such as CPI, FOMC, NFP, or rate decisions.",
      "metadata": { "category": "macro", "tags": ["news", "cpi", "fomc", "volatility"], "priority": "critical", "evidence_level": "education" }
    },
    {
      "title": "Funding Rate Extremes",
      "source_type": "strategy",
      "content_text": "Extremely positive funding rates may indicate crowded long positioning. Extremely negative funding rates may indicate crowded short positioning.",
      "metadata": { "category": "derivatives", "tags": ["funding_rate", "perpetuals", "sentiment"], "priority": "medium", "evidence_level": "education" }
    }
  ]
  $json$::jsonb) AS item(title text, source_type text, content_text text, metadata jsonb)
),
inserted_sources AS (
  INSERT INTO public.trading_knowledge_sources
    (user_id, title, source_type, content_text, metadata)
  SELECT
    NULL,
    p.title,
    p.source_type,
    p.content_text,
    p.metadata || jsonb_build_object(
      'scope', 'global',
      'seed', 'crypto_trading_knowledge_sample_2026_05_31'
    )
  FROM payload p
  WHERE NOT EXISTS (
    SELECT 1
    FROM public.trading_knowledge_sources existing
    WHERE existing.user_id IS NULL
      AND existing.title = p.title
      AND existing.metadata->>'seed' = 'crypto_trading_knowledge_sample_2026_05_31'
  )
  RETURNING id, title, content_text, metadata
)
INSERT INTO public.trading_knowledge_chunks
  (source_id, user_id, chunk_index, content, tags, metadata)
SELECT
  s.id,
  NULL,
  0,
  s.content_text,
  ARRAY(SELECT jsonb_array_elements_text(COALESCE(s.metadata->'tags', '[]'::jsonb))),
  jsonb_build_object('scope', 'global', 'source_title', s.title)
FROM inserted_sources s;

WITH eligible AS (
  SELECT
    s.id AS source_id,
    s.title,
    s.content_text,
    s.metadata,
    lower(COALESCE(s.metadata->>'priority', 'medium')) AS priority,
    lower(COALESCE(s.metadata->>'category', 'general')) AS category
  FROM public.trading_knowledge_sources s
  WHERE s.user_id IS NULL
    AND s.metadata->>'seed' = 'crypto_trading_knowledge_sample_2026_05_31'
    AND lower(COALESCE(s.metadata->>'priority', 'medium')) IN ('high', 'critical')
)
INSERT INTO public.trading_strategy_rules
  (user_id, source_id, rule_code, title, rule_text, category, severity, weight, metadata)
SELECT
  NULL,
  e.source_id,
  'seed_crypto_' || regexp_replace(lower(e.title), '[^a-z0-9]+', '_', 'g'),
  e.title,
  e.content_text,
  e.category,
  CASE WHEN e.priority = 'critical' THEN 'critical' ELSE 'high' END,
  CASE WHEN e.priority = 'critical' THEN 24 ELSE 16 END,
  jsonb_build_object('scope', 'global', 'seed', 'crypto_trading_knowledge_sample_2026_05_31')
FROM eligible e
WHERE NOT EXISTS (
  SELECT 1
  FROM public.trading_strategy_rules existing
  WHERE existing.rule_code = 'seed_crypto_' || regexp_replace(lower(e.title), '[^a-z0-9]+', '_', 'g')
);

COMMIT;
