# Agent Engine

The Agent Engine is the AI decision-making core of the lucrandos platform.
It consumes trading signals, runs them through a multi-agent pipeline, and writes
structured trade decisions to the database. It does **not** execute trades or
communicate with exchanges.

---

## Architecture

```
Signal (DB)
    ↓  [claimed by PollingConsumer]
LangGraph Pipeline
    ├── Data Agents         (fetch & validate market data)
    ├── Analysis Agents     (RSI, MACD, trend, momentum)  ← parallel
    ├── Critique Agents     (contrarian, manipulation)     ← parallel
    ├── Risk Agents         (auditor → CRO)               ← sequential, can veto
    ├── Security Agents     (guardian, injection defense)  ← parallel, can veto
    ├── Aggregator          (weighted score → decision)
    └── Evolution Agent     (observability report)
         ↓
TradeDecision (DB)
```

### Key properties

| Property | Value |
|---|---|
| Language | Python 3.11+ |
| Orchestration | LangGraph (StateGraph) |
| Data models | Pydantic v2 |
| Database | Supabase (PostgreSQL) via service role |
| Queue | DB polling (default) or PGMQ (optional) |
| Concurrency | `asyncio` + `asyncio.Semaphore` |
| Auth | None — internal service, no public API |

---

## Agents

| # | Agent | Category | Can Veto | Description |
|---|---|---|---|---|
| 1 | MarketDataAgent | data | ✗ | Fetches latest snapshot + price history |
| 2 | DataQualityAgent | data | ✓ | Validates OHLCV data quality |
| 3 | TechnicalAnalysisAgent | analysis | ✗ | RSI, MACD, EMA, Bollinger Bands |
| 4 | PriceActionAgent | analysis | ✗ | Trend detection, range position, momentum |
| 5 | MomentumAgent | analysis | ✗ | Price rate-of-change + volume confirmation |
| 6 | ContrarianAgent | critique | ✗ | Argues against the trade, finds failure scenarios |
| 7 | ManipulationDetectionAgent | critique | ✗ | Pump/dump, wash trading, spread anomalies |
| 8 | RiskAuditorAgent | risk | ✓ | ATR-based risk, accumulated flag review |
| 9 | ChiefRiskOfficerAgent | risk | ✓ | Bot limits, user settings, position sizing |
| 10 | SecurityGuardianAgent | security | ✓ | Symbol/exchange validation, metadata scan |
| 11 | PromptInjectionDefenseAgent | security | ✓ | Deep injection scan across all text fields |
| 12 | SystemEvolutionAgent | system_evolution | ✗ | Observability report (no decision impact) |

---

## Decision Flow

```
aggregated_score = weighted_sum(analysis + critique agents)
                 - data_quality_penalty
                 - manipulation_penalty
                 - risk_penalty

if veto_triggered:        → REJECT
elif score >= 70:         → OPEN_LONG / OPEN_SHORT
elif score >= 40:         → MANUAL_REVIEW
else:                     → WAIT
```

---

## Setup

### Prerequisites

- Python 3.11+
- A Supabase project with migrations 0001–0004 applied
- `uv` or `pip` for dependency management

### Install

```bash
cd agent-engine
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### Configure

```bash
cp .env.example .env
# Edit .env — fill in SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY
```

### Run (development)

```bash
# Dry run — no DB writes
DRY_RUN=true python -m src.main

# Normal run
python -m src.main
```

### Run (production)

```bash
# systemd service / Docker / Kubernetes — see deployment docs
python -m src.main
```

---

## Testing

```bash
# Unit tests only (no DB required)
pytest tests/ -v

# With coverage
pytest tests/ --cov=src --cov-report=term-missing

# Exclude integration tests (default in CI)
pytest tests/ -m "not integration"

# Integration tests (requires .env with live Supabase)
pytest tests/ -m integration
```

---

## Environment Variables

See `.env.example` for the full list with descriptions.

Required:
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

All others have safe defaults for development.

---

## Safety Guarantees

1. **No trade execution** — the engine writes decisions only. The Execution Engine
   (separate service) acts on them.

2. **Fail-closed** — any unexpected error in an agent returns `WAIT`, never
   `OPEN_LONG/SHORT`. The pipeline never opens a trade on an exception.

3. **Veto is absolute** — a single veto from any `can_veto=True` agent
   immediately terminates aggregation and forces `REJECT`.

4. **Service-role isolation** — `SUPABASE_SERVICE_ROLE_KEY` is used for all
   DB operations but is never logged, never returned in responses, and
   never placed in `PipelineState`.

5. **Injection defense** — two dedicated security agents scan all free-text
   inputs (signal metadata, agent reasoning strings) for injection patterns
   before the final decision is made.

6. **Dry run** — `DRY_RUN=true` runs the full pipeline but skips all DB writes.
   Safe to use against production Supabase for testing.

---

## Database Migrations

Apply in order:

| Migration | Description |
|---|---|
| 0001_initial_schema.sql | Full schema — 26 tables, enums, RLS, indexes |
| 0002_seed_agent_definitions.sql | Seeds 25 agent definitions |
| 0003_lock_core_pipeline_writes.sql | Removes authenticated INSERT/UPDATE on pipeline tables |
| 0004_signal_processing_lock.sql | Adds processing lock columns + partial indexes |

---

## Project Structure

```
agent-engine/
├── src/
│   ├── agents/
│   │   ├── base.py              # BaseAgent ABC
│   │   ├── data.py              # MarketDataAgent, DataQualityAgent
│   │   ├── analysis.py          # TechnicalAnalysis, PriceAction, Momentum
│   │   ├── critique.py          # Contrarian, ManipulationDetection
│   │   ├── risk.py              # RiskAuditor, ChiefRiskOfficer
│   │   ├── security.py          # SecurityGuardian, PromptInjectionDefense
│   │   ├── system_evolution.py  # SystemEvolution
│   │   └── __init__.py          # AGENT_REGISTRY
│   ├── db/
│   │   ├── models.py            # Pydantic v2 DB models
│   │   ├── repositories.py      # DB read/write layer
│   │   └── supabase_client.py   # Service-role client singleton
│   ├── orchestration/
│   │   ├── state.py             # PipelineState TypedDict
│   │   ├── aggregator.py        # Weighted score aggregation
│   │   ├── veto.py              # Veto detection + summary
│   │   └── graph.py             # LangGraph DAG
│   ├── queue/
│   │   ├── base.py              # BaseQueueConsumer ABC
│   │   ├── polling.py           # DB polling consumer
│   │   └── pgmq.py              # PGMQ consumer (optional)
│   ├── services/
│   │   ├── indicators.py        # Technical indicator functions
│   │   ├── market_data.py       # Market data service
│   │   ├── risk.py              # Risk calc helpers
│   │   ├── security.py          # Security check helpers
│   │   └── notifications.py     # Notification helpers
│   ├── utils/
│   │   └── time.py              # Time utilities
│   ├── config.py                # Settings (pydantic-settings)
│   ├── logging_config.py        # structlog setup
│   └── main.py                  # Entry point
├── tests/
│   ├── conftest.py              # Fixtures + model factories
│   ├── test_aggregator.py       # Score aggregation tests
│   ├── test_veto.py             # Veto logic tests
│   ├── test_agents.py           # Individual agent unit tests
│   └── test_pipeline.py         # End-to-end pipeline tests
├── .env.example
├── pyproject.toml
└── README.md
```
