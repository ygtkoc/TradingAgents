# Execution Engine

Converts approved `trade_decisions` into `trades`. The **only** service
allowed to create trade rows in the database.

---

## Architecture

```
trade_decisions (DB)
       │
       ▼ Phase 1 — fetch_executable_ids() (non-locking SELECT)
       │ Phase 2 — claim_for_execution()  (atomic UPDATE … RETURNING *)
       ▼
  ExecutionEngine.run()
       │
       ├── 0. ENABLE_LIVE_EXECUTION gate   (live only)
       ├── 1. Load context                 (bot, user_settings, exchange_account, market_snapshot)
       ├── 2. SecurityExecutionGuard       (15 checks — any failure → skip)
       ├── 3. IdempotencyChecker           (existing trade? → recover, no duplicate)
       ├── 4. RiskExecutionGuard           (14 checks — any critical failure → skip)
       ├── 5. OrderBuilder                 (derive side, quantity, price, clientOrderId)
       ├── 6. Executor
       │       ├── PaperExecutor   (MockAdapter, mode='paper')
       │       ├── ShadowExecutor  (no exchange call, mode='shadow')
       │       └── LiveExecutor    (real exchange, mode='live')
       ├── 7. mark_executed()              (decision.linked_trade_id = trade.id)
       ├── 8. AuditLog + TradeEvents
       └── 9. Notification
```

---

## Safety Invariants

| Invariant | How enforced |
|-----------|-------------|
| `ENABLE_LIVE_EXECUTION=false` by default | `settings.enable_live_execution` checked before live dispatch |
| Frontend/user input cannot create trades | Only this engine reads and claims `trade_decisions` |
| No duplicate trade per decision | Atomic Phase-2 claim + `IdempotencyChecker` + `linked_trade_id IS NULL` guard |
| Veto/injection blocks execution | `SecurityExecutionGuard` checks `veto_summary.vetoed` + `security_summary.injection_detected` |
| Paper/shadow never call exchange API | Routed to `PaperExecutor`/`ShadowExecutor` which use `MockExchangeAdapter` |
| Live fails closed on any uncertainty | All guards, every check, fail-closed; unknown exchange response → `mark_failed` (no blind retry) |
| API keys never logged | `ApiCredentials.__repr__` returns `REDACTED`; `zero_out()` called in `finally` |
| Atomic decision claim | Phase-2 `UPDATE … WHERE execution_status='pending_execution' AND linked_trade_id IS NULL` |
| No blind live retry | Unknown fill → `mark_failed`; pg_cron resets stuck `executing` rows after timeout |
| API key withdrawal permission | `BinanceExchangeAdapter.check_permissions()` raises `SecurityError` if `can_withdraw=True` |

---

## Execution Modes

| Mode | Exchange calls | Trade row | Status |
|------|---------------|-----------|--------|
| `paper` | None (MockAdapter) | Created, mode='paper', status='simulated' | For UI display |
| `shadow` | None | Created, mode='shadow', status='simulated' | For observation |
| `live` | Real (Binance etc.) | Created, mode='live', status='open' | Real orders |

---

## Setup

### 1. Prerequisites

- Python 3.11+
- Supabase project with migrations from `supabase/migrations/` applied

### 2. Install dependencies

```bash
cd execution-engine
pip install -e ".[dev]"
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env with your Supabase URL, service role key, and encryption secret
```

**Critical environment variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `SUPABASE_URL` | — | Your Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | — | Service role key (never expose to clients) |
| `API_KEY_ENCRYPTION_SECRET` | — | Must match the Edge Function encryption secret |
| `ENABLE_LIVE_EXECUTION` | `false` | Set `true` only after full safety audit |
| `DRY_RUN` | `false` | Skip all DB writes and exchange calls |

### 4. Apply database migrations

```bash
# From project root
supabase db push
# or apply manually:
psql $DATABASE_URL < supabase/migrations/0005_execution_engine.sql
```

### 5. Run

```bash
python -m src.main
```

---

## Running Tests

```bash
cd execution-engine
pytest tests/ -v
```

No real database or exchange connections are made in tests. All I/O is mocked.

```bash
# With coverage
pytest tests/ --cov=src --cov-report=term-missing
```

---

## Project Structure

```
execution-engine/
├── src/
│   ├── main.py                    # Entry point — polling loop + graceful shutdown
│   ├── config.py                  # Typed settings from environment
│   ├── logging_config.py          # structlog structured logging
│   ├── db/
│   │   ├── models.py              # Pydantic v2 models (TradeDecision, Bot, Trade…)
│   │   ├── repositories.py        # All DB reads/writes
│   │   └── supabase_client.py     # Singleton supabase-py client
│   ├── queue/
│   │   ├── base.py                # BaseQueueConsumer interface
│   │   ├── polling.py             # Two-phase polling consumer
│   │   └── pgmq.py                # PGMQ stub (future)
│   ├── guards/
│   │   ├── risk_guard.py          # RiskExecutionGuard (14 checks)
│   │   └── security_guard.py      # SecurityExecutionGuard (15 checks)
│   ├── execution/
│   │   ├── engine.py              # ExecutionEngine orchestrator
│   │   ├── idempotency.py         # Duplicate trade prevention
│   │   ├── order_builder.py       # OrderRequest construction
│   │   ├── paper_executor.py      # Paper mode execution
│   │   ├── shadow_executor.py     # Shadow mode execution
│   │   └── live_executor.py       # Live mode execution
│   ├── exchanges/
│   │   ├── base.py                # ExchangeAdapter ABC
│   │   ├── mock.py                # MockExchangeAdapter
│   │   ├── binance.py             # BinanceExchangeAdapter
│   │   └── factory.py             # get_paper_adapter / get_live_adapter
│   ├── keys/
│   │   └── key_provider.py        # AES-256-GCM key decryption + ApiCredentials
│   ├── services/
│   │   ├── market_data.py         # Market snapshot fetching
│   │   ├── notifications.py       # User notification stubs
│   │   └── recovery.py            # Partial failure recovery
│   └── utils/
│       ├── json.py                # JSON utilities
│       └── time.py                # UTC time helpers
├── tests/
│   ├── conftest.py                # Shared fixtures + model factories
│   ├── test_risk_guard.py         # RiskExecutionGuard tests
│   ├── test_security_guard.py     # SecurityExecutionGuard tests
│   ├── test_idempotency.py        # IdempotencyChecker tests
│   ├── test_paper_execution.py    # PaperExecutor + ShadowExecutor + OrderBuilder
│   ├── test_live_execution_disabled.py  # ENABLE_LIVE_EXECUTION gate tests
│   └── test_pipeline.py           # End-to-end engine orchestration tests
├── .env.example
├── pyproject.toml
└── README.md
```

---

## Adding a New Exchange

1. Create `src/exchanges/<exchange>.py` implementing `ExchangeAdapter`
2. Add the exchange name to `_SUPPORTED_LIVE_EXCHANGES` in `factory.py`
3. Add a branch to `get_live_adapter()` in `factory.py`
4. Ensure `check_permissions()` blocks if `can_withdraw=True`
5. Implement idempotent order placement via `clientOrderId` / equivalent

---

## Database Schema (key tables)

### `trade_decisions` (execution columns added by migration 0005)

| Column | Type | Description |
|--------|------|-------------|
| `execution_status` | `TEXT` | `pending_execution` → `executing` → `executed` / `failed` / `skipped` |
| `execution_worker_id` | `TEXT` | Worker that claimed the decision |
| `execution_started_at` | `TIMESTAMPTZ` | When Phase-2 claim succeeded |
| `execution_completed_at` | `TIMESTAMPTZ` | When mark_executed / mark_failed was called |
| `execution_error` | `TEXT` | Error message (truncated to 500 chars) |
| `execution_retry_count` | `INT` | Incremented by pg_cron on stuck reset |
| `linked_trade_id` | `UUID` | Set when a trade is created (idempotency anchor) |

### `trades`

| Column | Type | Description |
|--------|------|-------------|
| `mode` | `TEXT CHECK IN ('paper','live','shadow')` | Execution mode |
| `status` | `TEXT` | `open` / `simulated` / `closed` / `failed` |
| `exchange_order_id` | `TEXT` | Null for paper/shadow |
| `trade_decision_id` | `UUID` | FK to `trade_decisions` |

### `trade_events` (immutable append-only)

All execution lifecycle events: `paper_order_filled`, `live_order_placed`,
`live_order_filled`, `shadow_order_recorded`, `recovery_linked_existing_trade`.

---

## Recovery

### Stuck `executing` rows

A PostgreSQL function `release_stuck_executions()` is called by pg_cron every
5 minutes. It:
- Resets decisions stuck in `executing` for > `stale_minutes` back to `pending_execution`
- Increments `execution_retry_count`
- Marks permanently `failed` after `max_retry_count` attempts

### Partial failure (trade created, decision not linked)

If the trade row was created but `decision.linked_trade_id` was not updated
(network blip after DB write), the `IdempotencyChecker` will find the
existing trade on the next run and call `RecoveryService.recover_existing_trade()`
to link the decision without placing a second order.

---

## TODOs (before production)

- [ ] Integrate real notification backend (push / email / Realtime)
- [ ] Compute actual `daily_loss_usd` from `trades` table
- [ ] Implement portfolio exposure summing across open positions
- [ ] Add correlation risk check (cross-asset exposure)
- [ ] Add WebSocket fill confirmation for live orders (vs. REST polling)
- [ ] Add circuit breaker: N consecutive exchange failures → stop all execution
- [ ] Replace DB polling with PGMQ for lower latency
- [ ] Migrate API key storage to Supabase Vault or AWS KMS
- [ ] Add BINANCE_TESTNET=true env var for staging environment
- [ ] Validate filled_quantity and avg_fill_price against order request (anti-manipulation)
