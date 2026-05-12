# Autonomous Paper-Trading Driver

This service makes the TradingAgents platform self-driving for paper trading.
It runs in front of the three engines (agent · execution · position) and
provides the inputs they need to produce trades without manual interaction.

## Responsibilities

1. **Market Data Service** — streams live spot data for BTC/ETH/SOL from
   Binance public WebSockets, falls back to REST polling on disconnects, and
   writes `market_snapshots` rows on each closed candle.
2. **Paper Signal Seeder** — every 60 s, for each active paper bot with no
   pending signal, inserts a `signals` row of `signal_type='system'` so the
   Agent Engine can pick it up.
3. **Demo-bot bootstrap** — if no bots exist, creates three paper bots
   (BTC / ETH / SOL momentum) for the first user found.
4. **Health endpoint** — `GET /health` returns liveness + per-task state.

## Boundaries

- **No live execution.** Bots created here are always `mode='paper'`.
- **No frontend writes.** The autonomous service runs server-side only with
  `service_role`.
- **Reads from Binance public endpoints only.** No API keys required.

## Run locally

```bash
cp .env.example .env
# fill in SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY

pip install -e .
python -m src.main
```

Or, to boot this service together with the agent / execution / position
engines from one command, use the orchestrator at the repo root:

```bash
python scripts/dev_autonomous.py
```

## Health

```
$ curl http://localhost:9090/health
{"status":"ok","tasks":{"market_data":"running","seeder":"running","bootstrap":"running"},"snapshots_per_minute":3.0,"last_snapshot_age_s":4.2}
```
