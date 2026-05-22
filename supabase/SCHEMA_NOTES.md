# lucrandos Supabase SQL Foundation Notes

## Files
- `migrations/0001_initial_schema.sql` — Full schema, indexes, RLS, grants
- `migrations/0002_seed_agent_definitions.sql` — 25 agent definitions seed

---

## Architecture Decisions

### Unified `trades` table (no separate `paper_trades`)
A `trade_mode` enum column (`paper`/`live`/`shadow`) handles separation.
- Avoids ~95% schema duplication
- Single query path for analytics across modes
- Mode-switching bots work without data migration
- `exchange_order_id` is NULL for paper/shadow trades
- Partial index `idx_trades_live_open` isolates live positions for the risk engine

### Circular FK resolution
Two circular dependencies resolved with `DEFERRABLE INITIALLY DEFERRED` FKs:
- `bots.active_config_id` → `bot_configs`
- `trade_decisions.agent_run_id` → `agent_runs`

### `encrypted_api_keys` security contract
- RLS policy `encrypted_api_keys_deny_all` blocks all `authenticated` role access
- Only `service_role` (Edge Functions) can read/write
- Payloads are opaque `bytea` — encrypted by Edge Functions using **Supabase Vault** (`pgsodium`) before INSERT
- `vault_key_id` references the pgsodium key used for encryption
- Disable table exposure in Supabase Dashboard → Data API settings
- Never log payload columns in `audit_logs`

### Helper functions are `SECURITY DEFINER`
`is_admin()`, `is_super_admin()`, `is_security_admin()`, `get_user_role()` all run as the function owner (postgres), which bypasses RLS on their internal `SELECT FROM profiles`. This prevents infinite RLS recursion when `profiles` policies call `is_admin()`.

---

## What Must Live in Edge Functions (not SQL)

| Concern | Edge Function Responsibility |
|---|---|
| API key encryption | Encrypt with Vault before INSERT into `encrypted_api_keys` |
| API key decryption | Fetch + decrypt in Edge Function; never return raw payload to client |
| Withdrawal detection | Check `can_withdraw` from exchange API; write `withdrawal_detected = true` + insert `security_log` + reject key |
| Stripe webhooks | Insert/update `subscriptions` and `payments` tables using `service_role` |
| Bot mode → live promotion | Validate subscription allows live trading; set `real_trading_enabled` check |
| Audit log enrichment | Capture `ip_address`, `user_agent`, `session_id` from request context |
| Agent run orchestration | Start/update `agent_runs`; fan out to individual agents; write `agent_outputs`; compute `trade_decisions` |
| Real trade execution | Verify `trades.mode = 'live'`, `exchange_accounts.can_withdraw = false`, and subscription allows live trading before sending to exchange |
| Notification dispatch | Insert `notifications` rows + trigger push/email via Edge Function after trade events |

---

## RLS Policy Summary

| Table | User | Admin | super_admin | security_admin |
|---|---|---|---|---|
| profiles | own read/update (no role self-promo) | read+update all | read+update all | read+update all |
| user_settings | own CRUD | read all | read all | read all |
| exchange_accounts | own CRUD | read all | read all | read all |
| encrypted_api_keys | **BLOCKED** | **BLOCKED** | **BLOCKED** | **BLOCKED** |
| bots | own CRUD (delete only if archived) | read all | read all | read all |
| agent_definitions | read enabled only | read all | full CRUD | read all |
| agent_runs / outputs | own read | read all | read all | read all |
| market_snapshots | read all | read + insert | read + insert | read all |
| signals / trade_decisions / trades | own CRUD | read all | read all | read all |
| risk_logs / trade_events | own read | read all | read all | read all |
| security_logs | own read | — | read all | full CRUD |
| red_team_reports | **BLOCKED** | — | full CRUD | full CRUD |
| system_evolution_reports | **BLOCKED** | read+insert | full CRUD | read only |
| audit_logs | own read | read all | read all | read all |
| subscriptions / payments | own read | read all | read all | read all |

---

## Index Strategy

### Partial indexes (key patterns)
- `idx_bots_active` — only `status='active' AND is_archived=false` (hot path for bot orchestration)
- `idx_trades_open` — only `status='open'` (risk engine position check)
- `idx_trades_live_open` — only `mode='live' AND status='open'` (real-money exposure monitoring)
- `idx_agent_out_veto` — only `veto=true` (veto aggregation query)
- `idx_signals_pending` — only `status='pending'` (signal dispatch queue)
- `idx_td_manual_approval` — only `manual_approval_required=true AND approval_status='pending'`
- `idx_sec_log_critical` — only `severity IN ('high','critical') AND resolved=false`
- `idx_notif_unread` — only `is_read=false` (notification badge count)
- `idx_enc_keys_status` — only `key_status='active'` (active key lookup)
- `idx_exchange_acct_withdrawal` — only `withdrawal_detected=true` (security alerting)
- `idx_mkt_snap_recent` — 7-day sliding window for live dashboard queries

---

## Suggested Next Prompts

### Prompt 2 — Edge Functions Layer
> Build the Supabase Edge Functions for: (1) encrypted API key storage/retrieval using Vault, 
> (2) Stripe webhook handler for subscriptions/payments, (3) manual trade approval endpoint,
> (4) exchange account health check. Use TypeScript + Deno. Include auth middleware and audit logging.

### Prompt 3 — Python Agent Engine Foundation
> Build the Python agent orchestration engine. Use LangGraph or a custom DAG runner. 
> Agents read from Supabase via service_role. Each agent reads `agent_definitions`, 
> writes `agent_outputs`, and the orchestrator writes `agent_runs` and `trade_decisions`.
> Include retry logic, timeout enforcement, and veto short-circuit logic.

### Prompt 4 — Next.js Frontend Foundation  
> Build the Next.js 14 App Router frontend with Supabase Auth (SSR), protected routes,
> dashboard layout, bot management UI, trade history table, and notification bell.
> Use Supabase realtime subscriptions for live trade updates.

### Prompt 5 — Exchange Integration Layer
> Build the exchange adapter layer in Python. Start with Binance via ccxt.
> Implement: API key permission validation (reject withdrawal-enabled keys),
> market data streaming, order placement with circuit breakers, and health checks.
> Write results to Supabase via service_role.

### Prompt 6 — Risk Engine
> Build the risk engine as a Python service. It reads open positions from `trades`,
> user risk settings from `user_settings`, and bot config from `bot_configs`.
> Implement: daily loss limit circuit breaker, max position size validation,
> portfolio concentration check, and real-time PnL monitoring.
