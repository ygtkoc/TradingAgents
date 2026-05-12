import type { Trade, TradeMode, TradeDirection, TradeStatus, LifecycleStatus } from "@ta/types";

const SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"] as const;
const BOT_IDS = ["demo-bot-001", "demo-bot-002", "demo-bot-003"] as const;
const MODES: TradeMode[]        = ["paper", "shadow", "live"];
const DIRECTIONS: TradeDirection[] = ["long", "short"];

function pick<T>(arr: readonly T[], i: number): T {
  // safe under noUncheckedIndexedAccess: arr.length > 0 guaranteed by callers
  return arr[i % arr.length] as T;
}

function entryFor(symbol: string): number {
  switch (symbol) {
    case "BTC/USDT": return 60_000;
    case "ETH/USDT": return 3_200;
    case "SOL/USDT": return 145;
    default:         return 100;
  }
}

const DAY = 24 * 60 * 60 * 1000;

export const demoTrades: Trade[] = Array.from({ length: 25 }, (_, i) => {
  const symbol    = pick(SYMBOLS, i);
  const direction = pick(DIRECTIONS, i);
  const mode      = pick(MODES, i);
  const botId     = pick(BOT_IDS, i);
  const entry     = entryFor(symbol);

  // Distribute over the last 25 days
  const created = new Date(Date.now() - (24 - i) * DAY).toISOString();

  // First 17 closed, last 8 still open
  const isClosed = i < 17;
  const status:    TradeStatus    = isClosed ? "closed" : "open";
  const lifecycle: LifecycleStatus = isClosed
    ? "closed"
    : i % 9 === 8
      ? "needs_reconciliation"
      : "monitoring";

  // Pseudorandom but deterministic P&L
  const noise   = ((i * 7919) % 200 - 100) / 100; // [-1, 1)
  const drift   = direction === "long" ? 0.018 : -0.012;
  const pctMove = drift + noise * 0.025;
  const exit    = entry * (1 + pctMove);
  const qty     = symbol === "BTC/USDT" ? 0.05 : symbol === "ETH/USDT" ? 0.5 : 5;
  const pnl     = (exit - entry) * qty * (direction === "long" ? 1 : -1);

  return {
    id:                "demo-trade-" + String(i + 1).padStart(3, "0"),
    user_id:           "demo-user-00000000-0000-0000-0000-000000000001",
    bot_id:            botId,
    trade_decision_id: "demo-decision-" + String(i + 1).padStart(3, "0"),
    agent_run_id:      "demo-run-" + String(i + 1).padStart(3, "0"),

    exchange:        "binance",
    symbol,
    side:            direction === "long" ? "buy" : "sell",
    direction,
    mode,
    status,

    entry_price:     entry,
    quantity:        qty,
    filled_quantity: qty,
    avg_fill_price:  entry,

    stop_loss:       entry * (direction === "long" ? 0.97 : 1.03),
    take_profit:     entry * (direction === "long" ? 1.05 : 0.95),
    exit_price:      isClosed ? exit : null,
    avg_exit_price:  isClosed ? exit : null,

    unrealized_pnl:  isClosed ? null : pnl,
    realized_pnl:    isClosed ? pnl  : null,
    pnl:             isClosed ? pnl  : null,

    exchange_order_id: "demo-ord-" + (1000 + i),
    close_order_id:    isClosed ? "demo-close-" + (2000 + i) : null,
    close_reason:      isClosed ? (pnl >= 0 ? "take_profit" : "stop_loss") : null,

    lifecycle_status:           lifecycle,
    lifecycle_worker_id:        null,
    lifecycle_claimed_at:       null,
    lifecycle_last_checked_at:  created,
    lifecycle_error:            lifecycle === "needs_reconciliation"
                                  ? "Exchange reported partial fill — operator review required"
                                  : null,
    lifecycle_retry_count:      0,
    trailing_stop_price:        direction === "long" ? entry * 0.985 : entry * 1.015,
    highest_price_seen:         direction === "long" ? entry * 1.02 : null,
    lowest_price_seen:          direction === "short" ? entry * 0.98 : null,

    metadata:   {},
    created_at: created,
    updated_at: null,
    closed_at:  isClosed ? new Date(new Date(created).getTime() + 6 * 3_600_000).toISOString() : null,
  };
});
