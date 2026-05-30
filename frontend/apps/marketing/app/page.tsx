import Link from "next/link";

import { buttonVariants } from "@ta/ui";

export const revalidate = 30;

type DecisionRow = {
  id: string;
  symbol: string;
  direction?: string | null;
  mode?: string | null;
  final_decision: string;
  approval_status: string;
  score_summary?: Record<string, unknown> | null;
  created_at: string;
};

type TradeRow = {
  id: string;
  symbol: string;
  direction?: string | null;
  mode?: string | null;
  status: string;
  realized_pnl?: number | string | null;
  pnl_pct?: number | string | null;
  r_multiple?: number | string | null;
  close_reason?: string | null;
  closed_at?: string | null;
  created_at: string;
};

type MarketMove = {
  symbol: string;
  change24h: number;
  price?: number;
};

const fallbackDecisions: DecisionRow[] = [
  {
    id: "demo-btc",
    symbol: "BTCUSDT",
    direction: "long",
    mode: "paper",
    final_decision: "open_long",
    approval_status: "auto_approved",
    score_summary: { aggregated_score: 82, confidence: 0.76 },
    created_at: new Date(Date.now() - 1000 * 60 * 7).toISOString(),
  },
  {
    id: "demo-eth",
    symbol: "ETHUSDT",
    direction: "short",
    mode: "paper",
    final_decision: "hold",
    approval_status: "pending",
    score_summary: { aggregated_score: 54, confidence: 0.58 },
    created_at: new Date(Date.now() - 1000 * 60 * 18).toISOString(),
  },
  {
    id: "demo-sol",
    symbol: "SOLUSDT",
    direction: "long",
    mode: "shadow",
    final_decision: "manual_approval_required",
    approval_status: "pending",
    score_summary: { aggregated_score: 68, confidence: 0.64 },
    created_at: new Date(Date.now() - 1000 * 60 * 29).toISOString(),
  },
];

const fallbackTrades: TradeRow[] = [
  {
    id: "closed-btc",
    symbol: "BTCUSDT",
    direction: "long",
    mode: "paper",
    status: "closed",
    r_multiple: 2.1,
    close_reason: "take_profit",
    closed_at: new Date(Date.now() - 1000 * 60 * 44).toISOString(),
    created_at: new Date(Date.now() - 1000 * 60 * 84).toISOString(),
  },
  {
    id: "closed-eth",
    symbol: "ETHUSDT",
    direction: "short",
    mode: "paper",
    status: "closed",
    r_multiple: -1,
    close_reason: "stop_loss",
    closed_at: new Date(Date.now() - 1000 * 60 * 92).toISOString(),
    created_at: new Date(Date.now() - 1000 * 60 * 132).toISOString(),
  },
  {
    id: "closed-sol",
    symbol: "SOLUSDT",
    direction: "long",
    mode: "shadow",
    status: "closed",
    r_multiple: 1.4,
    close_reason: "manual",
    closed_at: new Date(Date.now() - 1000 * 60 * 156).toISOString(),
    created_at: new Date(Date.now() - 1000 * 60 * 210).toISOString(),
  },
];

const fallbackMoves: Record<string, MarketMove> = {
  BTCUSDT: { symbol: "BTCUSDT", change24h: 1.84 },
  ETHUSDT: { symbol: "ETHUSDT", change24h: -0.72 },
  SOLUSDT: { symbol: "SOLUSDT", change24h: 4.16 },
};

function getCustomerSignInUrl() {
  const configuredUrl = process.env.NEXT_PUBLIC_CUSTOMER_URL?.replace(/\/$/, "");
  const customerUrl =
    configuredUrl && !configuredUrl.includes("localhost")
      ? configuredUrl
      : "https://customer.lucrandos.com";

  return `${customerUrl}/sign-in`;
}

function getSupabaseHeaders() {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL?.replace(/\/$/, "");
  const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  const authKey = serviceRoleKey ?? anonKey;

  if (!supabaseUrl || !authKey) {
    return null;
  }

  return {
    supabaseUrl,
    headers: {
      apikey: authKey,
      authorization: `Bearer ${authKey}`,
    },
  };
}

async function fetchSupabaseRows<T>(query: string): Promise<T[]> {
  const config = getSupabaseHeaders();

  if (!config) {
    return [];
  }

  try {
    const response = await fetch(`${config.supabaseUrl}/rest/v1/${query}`, {
      headers: config.headers,
      next: { revalidate: 30 },
    });

    if (!response.ok) {
      return [];
    }

    const rows = (await response.json()) as unknown;
    return Array.isArray(rows) ? (rows as T[]) : [];
  } catch {
    return [];
  }
}

async function fetchRecentDecisions() {
  const rows = await fetchSupabaseRows<DecisionRow>(
    "trade_decisions?select=id,symbol,direction,mode,final_decision,approval_status,score_summary,created_at&order=created_at.desc&limit=5",
  );

  return rows.length > 0 ? rows : fallbackDecisions;
}

async function fetchClosedTrades() {
  const rows = await fetchSupabaseRows<TradeRow>(
    "trades?select=id,symbol,direction,mode,status,realized_pnl,pnl_pct,r_multiple,close_reason,closed_at,created_at&status=eq.closed&order=closed_at.desc.nullslast&limit=5",
  );

  return rows.length > 0 ? rows : fallbackTrades;
}

function normalizeMarketSymbol(symbol: string) {
  const cleanSymbol = symbol.replace(/[^a-zA-Z0-9]/g, "").toUpperCase();

  if (cleanSymbol.endsWith("USDT")) {
    return cleanSymbol;
  }

  if (cleanSymbol.endsWith("USD")) {
    return `${cleanSymbol.slice(0, -3)}USDT`;
  }

  return `${cleanSymbol}USDT`;
}

async function fetchMarketMove(symbol: string): Promise<MarketMove | null> {
  const marketSymbol = normalizeMarketSymbol(symbol);

  try {
    const response = await fetch(`https://api.binance.com/api/v3/ticker/24hr?symbol=${marketSymbol}`, {
      next: { revalidate: 30 },
    });

    if (!response.ok) {
      return fallbackMoves[marketSymbol] ?? null;
    }

    const data = (await response.json()) as { priceChangePercent?: string; lastPrice?: string };

    return {
      symbol: marketSymbol,
      change24h: Number(data.priceChangePercent ?? 0),
      price: Number(data.lastPrice ?? 0),
    };
  } catch {
    return fallbackMoves[marketSymbol] ?? null;
  }
}

async function getMarketMoves(symbols: string[]) {
  const uniqueSymbols = Array.from(new Set(symbols.map(normalizeMarketSymbol))).slice(0, 8);
  const moves = await Promise.all(uniqueSymbols.map(fetchMarketMove));

  return moves.reduce<Record<string, MarketMove>>((acc, move) => {
    if (move) {
      acc[move.symbol] = move;
    }

    return acc;
  }, {});
}

function getScore(decision: DecisionRow) {
  const score = decision.score_summary?.aggregated_score ?? decision.score_summary?.score;
  const numericScore = Number(score);

  return Number.isFinite(numericScore) ? Math.round(numericScore) : null;
}

function formatLabel(value?: string | null) {
  return (value ?? "unknown").replaceAll("_", " ").toUpperCase();
}

function formatTime(value?: string | null) {
  if (!value) {
    return "just now";
  }

  const diffMinutes = Math.max(1, Math.round((Date.now() - new Date(value).getTime()) / 60000));

  if (diffMinutes < 60) {
    return `${diffMinutes}m ago`;
  }

  return `${Math.round(diffMinutes / 60)}h ago`;
}

function formatPercent(value?: number) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "0.00%";
  }

  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatR(value?: number | string | null) {
  const numericValue = Number(value);

  if (!Number.isFinite(numericValue)) {
    return "0.0R";
  }

  return `${numericValue > 0 ? "+" : ""}${numericValue.toFixed(1)}R`;
}

function toneForChange(value?: number) {
  if (typeof value !== "number") {
    return "border-white/10 bg-white/[0.04] text-zinc-300";
  }

  return value >= 0
    ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-200"
    : "border-rose-400/25 bg-rose-400/10 text-rose-200";
}

function toneForDecision(decision: string) {
  if (decision.includes("open_long")) {
    return "border-emerald-400/30 bg-emerald-400/10 text-emerald-200";
  }

  if (decision.includes("open_short")) {
    return "border-rose-400/30 bg-rose-400/10 text-rose-200";
  }

  if (decision.includes("manual")) {
    return "border-amber-300/30 bg-amber-300/10 text-amber-100";
  }

  return "border-sky-300/25 bg-sky-300/10 text-sky-100";
}

function toneForR(value?: number | string | null) {
  const numericValue = Number(value);

  return numericValue >= 0
    ? "text-emerald-200"
    : "text-rose-200";
}

export default async function HomePage() {
  const customerSignInUrl = getCustomerSignInUrl();
  const [decisions, closedTrades] = await Promise.all([fetchRecentDecisions(), fetchClosedTrades()]);
  const marketMoves = await getMarketMoves([
    ...decisions.map((decision) => decision.symbol),
    ...closedTrades.map((trade) => trade.symbol),
  ]);
  const activeDecisionCount = decisions.filter((decision) => decision.approval_status !== "rejected").length;
  const positiveClosedTrades = closedTrades.filter((trade) => Number(trade.r_multiple) > 0).length;

  return (
    <main className="min-h-screen overflow-hidden bg-[#07090b] text-zinc-50">
      <div className="pointer-events-none fixed inset-0 bg-[linear-gradient(rgba(255,255,255,0.055)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.055)_1px,transparent_1px)] bg-[size:72px_72px] opacity-40" />
      <div className="pointer-events-none fixed inset-x-0 top-0 h-80 bg-[radial-gradient(circle_at_35%_20%,rgba(20,184,166,0.18),transparent_34%),radial-gradient(circle_at_74%_8%,rgba(251,191,36,0.13),transparent_28%)]" />

      <div className="relative mx-auto flex min-h-screen max-w-7xl flex-col px-5 py-6 sm:px-8 lg:px-10">
        <nav className="flex items-center justify-between gap-4">
          <Link href="/" className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-teal-300/35 bg-teal-300/10 text-sm font-semibold text-teal-100">
              L
            </div>
            <div>
              <div className="text-sm font-semibold text-zinc-50">lucrandos</div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-teal-200/70">AI trading OS</div>
            </div>
          </Link>
          <div className="flex items-center gap-2">
            <Link
              href="/pricing"
              className={buttonVariants({
                variant: "outline",
                className: "hidden border-white/15 bg-white/[0.03] text-zinc-100 hover:bg-white/[0.08] sm:inline-flex",
              })}
            >
              Pricing
            </Link>
            <Link href={customerSignInUrl} className={buttonVariants({ className: "bg-teal-300 text-zinc-950 hover:bg-teal-200" })}>
              Sign in
            </Link>
          </div>
        </nav>

        <section className="grid flex-1 items-center gap-9 py-10 lg:grid-cols-[0.9fr_1.1fr] lg:py-14">
          <div className="max-w-2xl space-y-7">
            <div className="inline-flex items-center gap-2 rounded-lg border border-emerald-300/25 bg-emerald-300/10 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-emerald-100">
              <span className="h-2 w-2 rounded-full bg-emerald-300 shadow-[0_0_18px_rgba(110,231,183,0.85)]" />
              Live agent decisions
            </div>
            <div className="space-y-5">
              <h1 className="text-5xl font-semibold leading-[0.96] tracking-[0] text-zinc-50 sm:text-6xl lg:text-7xl">
                Market actions, risk results, and coin momentum on one screen.
              </h1>
              <p className="max-w-xl text-base leading-8 text-zinc-300">
                Lucrandos shows the latest agent decisions, closed trade outcomes, and the 24 hour market move behind each symbol.
              </p>
            </div>
            <div className="grid max-w-xl grid-cols-3 gap-3">
              {[
                ["Active", activeDecisionCount.toString()],
                ["Closed", closedTrades.length.toString()],
                ["Winners", `${positiveClosedTrades}/${closedTrades.length}`],
              ].map(([label, value]) => (
                <div key={label} className="rounded-lg border border-white/10 bg-white/[0.045] p-4">
                  <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-zinc-400">{label}</div>
                  <div className="mt-2 text-2xl font-semibold text-zinc-50">{value}</div>
                </div>
              ))}
            </div>
            <div className="flex flex-wrap gap-3">
              <Link href={customerSignInUrl} className={buttonVariants({ size: "lg", className: "bg-teal-300 text-zinc-950 hover:bg-teal-200" })}>
                Open command center
              </Link>
              <Link
                href="/pricing"
                className={buttonVariants({
                  variant: "outline",
                  size: "lg",
                  className: "border-white/15 bg-white/[0.03] text-zinc-100 hover:bg-white/[0.08]",
                })}
              >
                Pricing
              </Link>
            </div>
          </div>

          <div className="space-y-4">
            <div className="rounded-lg border border-white/10 bg-zinc-950/70 p-4 shadow-2xl shadow-black/35 backdrop-blur">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-zinc-50">Decision tape</div>
                  <div className="text-xs text-zinc-400">Latest agent output and market move</div>
                </div>
                <div className="rounded-lg border border-teal-300/20 bg-teal-300/10 px-3 py-1 text-xs font-semibold text-teal-100">
                  {formatTime(decisions[0]?.created_at)}
                </div>
              </div>

              <div className="grid gap-3">
                {decisions.map((decision) => {
                  const marketSymbol = normalizeMarketSymbol(decision.symbol);
                  const marketMove = marketMoves[marketSymbol] ?? fallbackMoves[marketSymbol];
                  const score = getScore(decision);

                  return (
                    <div key={decision.id} className="rounded-lg border border-white/10 bg-white/[0.035] p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-lg font-semibold text-zinc-50">{decision.symbol}</span>
                            <span className={`rounded-md border px-2 py-1 text-[10px] font-semibold ${toneForDecision(decision.final_decision)}`}>
                              {formatLabel(decision.final_decision)}
                            </span>
                          </div>
                          <div className="mt-2 text-xs text-zinc-400">
                            {formatLabel(decision.mode)} / {formatLabel(decision.approval_status)} / {formatTime(decision.created_at)}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <div className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-right">
                            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-zinc-500">Score</div>
                            <div className="text-sm font-semibold text-zinc-50">{score ?? "--"}</div>
                          </div>
                          <div className={`rounded-lg border px-3 py-2 text-right ${toneForChange(marketMove?.change24h)}`}>
                            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] opacity-70">24h</div>
                            <div className="text-sm font-semibold">{formatPercent(marketMove?.change24h)}</div>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="rounded-lg border border-white/10 bg-[#11120f]/80 p-4 backdrop-blur">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <div className="text-sm font-semibold text-zinc-50">Closed trades</div>
                  <div className="text-xs text-zinc-400">Realized R multiple and current symbol movement</div>
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                {closedTrades.slice(0, 3).map((trade) => {
                  const marketSymbol = normalizeMarketSymbol(trade.symbol);
                  const marketMove = marketMoves[marketSymbol] ?? fallbackMoves[marketSymbol];

                  return (
                    <div key={trade.id} className="rounded-lg border border-white/10 bg-white/[0.04] p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-sm font-semibold text-zinc-50">{trade.symbol}</div>
                          <div className="mt-1 text-[11px] uppercase tracking-[0.12em] text-zinc-500">
                            {formatLabel(trade.close_reason)} / {formatTime(trade.closed_at ?? trade.created_at)}
                          </div>
                        </div>
                        <div className={`text-xl font-semibold ${toneForR(trade.r_multiple)}`}>{formatR(trade.r_multiple)}</div>
                      </div>
                      <div className={`mt-4 inline-flex rounded-md border px-2 py-1 text-xs font-semibold ${toneForChange(marketMove?.change24h)}`}>
                        {formatPercent(marketMove?.change24h)} 24h
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
