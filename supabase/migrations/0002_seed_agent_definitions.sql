-- ============================================================
-- TradingAgents Platform — Agent Definitions Seed
-- Migration: 0002_seed_agent_definitions.sql
-- Run after: 0001_initial_schema.sql
--
-- Inserts the canonical agent catalog.
-- All agents are disabled by default; super_admin enables them.
-- ============================================================

INSERT INTO public.agent_definitions
  (name, display_name, agent_type, category, description, enabled, can_veto, default_weight, timeout_seconds, version, tags)
VALUES

-- ── DATA AGENTS ─────────────────────────────────────────────
('market_data_agent',
 'Market Data Agent', 'hybrid', 'data',
 'Fetches and normalizes OHLCV, order book, and funding rate data from exchanges.',
 true, false, 1.0, 15, '1.0.0',
 ARRAY['data', 'market', 'ohlcv']),

('sentiment_data_agent',
 'Sentiment Data Agent', 'llm', 'data',
 'Aggregates sentiment signals from news, social media, and on-chain data sources.',
 true, false, 1.0, 30, '1.0.0',
 ARRAY['data', 'sentiment', 'nlp']),

('on_chain_data_agent',
 'On-Chain Data Agent', 'rule_based', 'data',
 'Fetches on-chain metrics: exchange inflows/outflows, whale wallets, staking flows.',
 false, false, 0.8, 20, '1.0.0',
 ARRAY['data', 'on-chain', 'blockchain']),

-- ── ANALYSIS AGENTS ─────────────────────────────────────────
('technical_analysis_agent',
 'Technical Analysis Agent', 'rule_based', 'analysis',
 'Computes technical indicators (RSI, MACD, Bollinger Bands, ATR, EMA/SMA) and identifies patterns.',
 true, false, 1.5, 20, '1.0.0',
 ARRAY['analysis', 'technical', 'indicators']),

('trend_analysis_agent',
 'Trend Analysis Agent', 'ml_model', 'analysis',
 'Multi-timeframe trend detection using ML classification models.',
 true, false, 1.5, 25, '1.0.0',
 ARRAY['analysis', 'trend', 'ml']),

('liquidity_analysis_agent',
 'Liquidity Analysis Agent', 'rule_based', 'analysis',
 'Evaluates order book depth, spread, slippage estimates, and liquidity conditions.',
 true, false, 1.2, 15, '1.0.0',
 ARRAY['analysis', 'liquidity', 'order-book']),

('sentiment_analysis_agent',
 'Sentiment Analysis Agent', 'llm', 'analysis',
 'Scores market sentiment from aggregated data and produces a directional sentiment signal.',
 true, false, 1.0, 30, '1.0.0',
 ARRAY['analysis', 'sentiment', 'llm']),

('correlation_analysis_agent',
 'Correlation Analysis Agent', 'ml_model', 'analysis',
 'Detects cross-asset correlations and portfolio concentration risk signals.',
 false, false, 0.8, 20, '1.0.0',
 ARRAY['analysis', 'correlation', 'portfolio']),

-- ── CRITIQUE AGENTS ─────────────────────────────────────────
('bull_case_agent',
 'Bull Case Agent', 'llm', 'critique',
 'Constructs the strongest bullish argument for the current signal.',
 true, false, 1.0, 30, '1.0.0',
 ARRAY['critique', 'bull', 'debate']),

('bear_case_agent',
 'Bear Case Agent', 'llm', 'critique',
 'Constructs the strongest bearish counter-argument for the current signal.',
 true, false, 1.0, 30, '1.0.0',
 ARRAY['critique', 'bear', 'debate']),

('devil_advocate_agent',
 'Devil''s Advocate Agent', 'llm', 'critique',
 'Challenges the prevailing consensus with contrarian analysis to prevent groupthink.',
 true, false, 0.8, 30, '1.0.0',
 ARRAY['critique', 'contrarian', 'debate']),

-- ── RISK AGENTS ─────────────────────────────────────────────
('position_risk_agent',
 'Position Risk Agent', 'rule_based', 'risk',
 'Validates position size, stop-loss distance, and risk-per-trade against user settings.',
 true, true, 2.0, 10, '1.0.0',
 ARRAY['risk', 'position', 'sizing']),

('portfolio_risk_agent',
 'Portfolio Risk Agent', 'rule_based', 'risk',
 'Checks portfolio-level exposure: max open positions, daily loss limits, drawdown circuit breakers.',
 true, true, 2.0, 10, '1.0.0',
 ARRAY['risk', 'portfolio', 'drawdown']),

('volatility_risk_agent',
 'Volatility Risk Agent', 'ml_model', 'risk',
 'Assesses market volatility conditions; vetoes trades during extreme volatility events.',
 true, true, 1.8, 15, '1.0.0',
 ARRAY['risk', 'volatility', 'vix']),

-- ── SECURITY AGENTS ─────────────────────────────────────────
('manipulation_detection_agent',
 'Manipulation Detection Agent', 'ml_model', 'security',
 'Detects pump-and-dump patterns, wash trading, and anomalous order book activity.',
 true, true, 2.0, 20, '1.0.0',
 ARRAY['security', 'manipulation', 'fraud']),

('security_red_team_agent',
 'Security Red Team Agent', 'llm', 'security',
 'Periodically audits platform security posture and generates red_team_reports.',
 true, false, 1.0, 120, '1.0.0',
 ARRAY['security', 'audit', 'red-team']),

('api_key_health_agent',
 'API Key Health Agent', 'rule_based', 'security',
 'Monitors API key expiry, rotation schedule, and validates permission flags.',
 true, false, 1.5, 10, '1.0.0',
 ARRAY['security', 'api-keys', 'health']),

-- ── EXECUTION AGENTS ────────────────────────────────────────
('execution_agent',
 'Execution Agent', 'rule_based', 'execution',
 'Translates approved trade decisions into exchange orders with slippage protection.',
 true, false, 1.0, 15, '1.0.0',
 ARRAY['execution', 'orders', 'exchange']),

('order_management_agent',
 'Order Management Agent', 'rule_based', 'execution',
 'Manages live order state: partial fills, cancellations, and order book re-entries.',
 true, false, 1.0, 15, '1.0.0',
 ARRAY['execution', 'order-management', 'fills']),

-- ── MONITORING AGENTS ───────────────────────────────────────
('position_monitor_agent',
 'Position Monitor Agent', 'rule_based', 'monitoring',
 'Continuously monitors open positions for stop-loss, take-profit, and trailing stop triggers.',
 true, false, 1.5, 10, '1.0.0',
 ARRAY['monitoring', 'positions', 'stops']),

('bot_health_monitor_agent',
 'Bot Health Monitor Agent', 'rule_based', 'monitoring',
 'Monitors bot operational health: error rates, latency, stalled runs, exchange connectivity.',
 true, false, 1.0, 10, '1.0.0',
 ARRAY['monitoring', 'health', 'alerts']),

-- ── POST-TRADE AGENTS ────────────────────────────────────────
('trade_review_agent',
 'Trade Review Agent', 'llm', 'post_trade',
 'Post-trade analysis: decision quality scoring, what-if analysis, lessons learned.',
 true, false, 1.0, 60, '1.0.0',
 ARRAY['post-trade', 'review', 'analytics']),

('performance_attribution_agent',
 'Performance Attribution Agent', 'ml_model', 'post_trade',
 'Attributes PnL to strategy factors: signal quality, timing, sizing, market conditions.',
 false, false, 0.8, 60, '1.0.0',
 ARRAY['post-trade', 'attribution', 'pnl']),

-- ── SYSTEM EVOLUTION AGENTS ──────────────────────────────────
('agent_gap_finder_agent',
 'Agent Gap Finder Agent', 'llm', 'system_evolution',
 'Identifies missing agent coverage in the pipeline and generates system_evolution_reports.',
 true, false, 1.0, 120, '1.0.0',
 ARRAY['system-evolution', 'gaps', 'recommendations']),

('database_schema_auditor_agent',
 'Database Schema Auditor Agent', 'llm', 'system_evolution',
 'Audits the live database schema for missing indexes, RLS gaps, and security issues.',
 true, false, 1.0, 120, '1.0.0',
 ARRAY['system-evolution', 'schema', 'audit'])

ON CONFLICT (name) DO UPDATE SET
  display_name    = EXCLUDED.display_name,
  description     = EXCLUDED.description,
  version         = EXCLUDED.version,
  updated_at      = NOW();
