---
name: TradingAgents Project Foundation
description: Core architecture decisions, tech stack, and completed work for the multi-agent AI trading SaaS platform
type: project
---

Multi-agent AI trading SaaS platform. Phase 1 complete: Supabase SQL foundation.

**Why:** Building a production platform where AI agents analyze markets, manage risk, and execute trades on behalf of users.

## Tech Stack
- Frontend (future): Next.js 14 + TypeScript + Supabase SSR
- Backend: Supabase (PostgreSQL + Auth + RLS + Edge Functions + Realtime)
- Agent Engine (future): Python (LangGraph or custom DAG)
- Payments (future): Stripe
- Queue (future): Supabase PGMQ

## Completed: SQL Foundation
Files in `supabase/migrations/`:
- `0001_initial_schema.sql` — 26 tables, all enums, RLS policies, indexes, helper functions, grants
- `0002_seed_agent_definitions.sql` — 25 agent definitions seeded

## Key Architecture Decisions
- Unified `trades` table with `trade_mode` enum (no separate paper_trades table)
- `encrypted_api_keys` blocked entirely for `authenticated` role — service_role Edge Function only
- Withdrawal-enabled API keys rejected at application level; DB has `can_withdraw` CHECK constraint = false
- Helper functions (`is_admin`, `is_super_admin`, `is_security_admin`) are SECURITY DEFINER to avoid RLS recursion
- 5 user roles: user, pro_user, admin, super_admin, security_admin
- 9 agent categories: data, analysis, critique, risk, security, execution, monitoring, post_trade, system_evolution

## Agent Definitions (25 total)
- data (3): market_data, sentiment_data, on_chain_data
- analysis (5): technical, trend, liquidity, sentiment, correlation
- critique (3): bull_case, bear_case, devil_advocate
- risk (3): position_risk, portfolio_risk, volatility_risk (all can_veto=true)
- security (3): manipulation_detection (can_veto), red_team, api_key_health
- execution (2): execution, order_management
- monitoring (2): position_monitor, bot_health_monitor
- post_trade (2): trade_review, performance_attribution
- system_evolution (2): agent_gap_finder, database_schema_auditor

## Completed: Security Patch
- `0003_lock_core_pipeline_writes.sql` — drops INSERT/UPDATE policies + revokes grants on agent_runs, agent_outputs, signals, trade_decisions, trades, trade_events, risk_logs. Service_role only writes.

## Completed: Edge Functions Layer (Phase 2)
All files in `supabase/functions/`. 25 files, 3,103 lines.

### Shared utilities (`_shared/`)
- `config.ts` — env vars with boot-time validation
- `errors.ts` — HttpError class + Errors factory
- `cors.ts` — origin allowlist (ornek.com, musteri.ornek.com, admin.ornek.com, localhost)
- `response.ts` — jsonResponse, errorResponse, withErrorHandler wrapper
- `supabase.ts` — createSupabaseUserClient (RLS applies), createSupabaseServiceClient (bypasses RLS)
- `auth.ts` — getAuthenticatedUser, getUserProfile, requireAdmin/SuperAdmin/SecurityAdmin
- `audit.ts` — writeAuditLog, writeSecurityLog (non-throwing)
- `validation.ts` — Zod schemas for all 9 functions
- `ownership.ts` — assertUserOwnsBot, assertUserOwnsExchangeAccount, assertUserOwnsTradeDecision
- `encryption.ts` — AES-256-GCM (Web Crypto API); TODO: migrate to Supabase Vault
- `exchange/` — ExchangeAdapter interface + MockExchangeAdapter + factory

### Edge Functions
- `store-exchange-api-key` — validates perms, rejects withdrawal keys, encrypts + stores
- `revoke-exchange-api-key` — marks revoked, deactivates account, pauses linked bots
- `manual-trade-approval` — approve/reject with optimistic concurrency guard
- `create-manual-signal` — user-triggered signal (still flows through full pipeline)
- `bot-control` — state machine (start/pause/stop/archive/unarchive) with live bot guards
- `exchange-health-check` — decrypts key in memory, calls exchange, discards plaintext
- `stripe-webhook` — deployed --no-verify-jwt; signature verification via Stripe SDK
- `admin-security-action` — resolve logs, ban/unban users, pause trading (role-gated)
- `create-notification` — admin-only notification creation

### Key patterns
- All functions: CORS preflight → JWT verify → Zod validate → ownership check → service_role write → audit log
- API keys: encrypted with AES-256-GCM per-field (IV+ciphertext as base64 bytea); plaintext never logged/returned
- Bot start (live): checks real_trading_enabled, subscription.real_trading_allowed, exchange account safety
- stripe-webhook: `--no-verify-jwt` deployment; Stripe signature verified before any processing
- TODO(queue): PGMQ publish points marked in manual-trade-approval and create-manual-signal

**How to apply:** Reference exact function IDs [EF-KEY-01], [EF-KEY-02], etc. when discussing the Edge Function layer. Next: Python Agent Engine, Next.js frontend, exchange adapters.
