"use client";

import { useEffect, useMemo, useState } from "react";
import { Button, Card, CardContent, CardHeader, CardTitle, Input } from "@ta/ui";
import { cn, formatCurrency } from "@ta/utils";

import { supabase } from "@/lib/supabase/client";
import { useCurrentUser } from "@/lib/hooks/queries/use-current-user";

const PAIRS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "HBARUSDT", "CHZUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT"];

type Direction = "long" | "short";
type Candle = { close: number; open: number; time: number };
type Book = { askPrice: number; askQty: number; bidPrice: number; bidQty: number };
type Ticker = { change24h: number; lastPrice: number };

export default function MarketsPage() {
  const { data: user } = useCurrentUser();
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [direction, setDirection] = useState<Direction>("long");
  const [entry, setEntry] = useState("");
  const [stop, setStop] = useState("");
  const [risk, setRisk] = useState("1");
  const [ticker, setTicker] = useState<Ticker | null>(null);
  const [book, setBook] = useState<Book | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [busy, setBusy] = useState(false);

  const normalized = normalizeSymbol(symbol);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const [tickerNext, bookNext, candlesNext] = await Promise.all([
        fetchTicker(normalized),
        fetchBook(normalized),
        fetchCandles(normalized),
      ]);
      if (cancelled) return;
      setTicker(tickerNext);
      setBook(bookNext);
      setCandles(candlesNext);
      if (tickerNext?.lastPrice && !entry) setEntry(String(trim(tickerNext.lastPrice)));
    }
    void load();
    const timer = window.setInterval(() => void load(), 2500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [entry, normalized]);

  const plan = useMemo(() => {
    const e = parseNum(entry);
    const s = parseNum(stop);
    if (!e || !s || e === s) return null;
    const r = Math.abs(e - s);
    return {
      entry: e,
      stop: s,
      riskPct: parseNum(risk) ?? 1,
      r,
      levels: [1, 2, 3].map((multiple) => direction === "short" ? e - r * multiple : e + r * multiple),
    };
  }, [direction, entry, risk, stop]);

  async function submit() {
    if (!user || !plan) return;
    const ok = window.confirm(`${direction.toUpperCase()} ${normalized}\nEntry ${fmt(plan.entry)}\nStop ${fmt(plan.stop)}\nTP3 ${fmt(plan.levels[2])}\n\nOnaylıyor musunuz?`);
    if (!ok) return;
    setBusy(true);
    const { error } = await supabase.from("trade_decisions").insert({
      user_id: user.id,
      symbol: normalized,
      direction,
      mode: "paper",
      final_decision: direction === "short" ? "open_short" : "open_long",
      approval_status: "approved",
      execution_status: "pending_execution",
      manual_approval_required: false,
      score_summary: { source: "web_markets", aggregated_score: 100 },
      risk_summary: {
        source: "web_markets",
        entry_price: plan.entry,
        stop_loss: plan.stop,
        take_profit: plan.levels[2],
        risk_percent: plan.riskPct,
        reward_plan: {
          levels: plan.levels.map((target, index) => ({
            target_price: target,
            r_multiple: index + 1,
            size_pct: index === 2 ? 34 : 33,
          })),
        },
      },
      security_summary: { verdict: "manual_web_order" },
      metadata: { source: "web_markets", selected_wallet: "paper" },
    });
    setBusy(false);
    if (error) window.alert(error.message);
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-[0] text-foreground">Markets</h1>
        <p className="mt-1 text-sm text-muted-foreground">Live price, book pressure, chart, and manual paper order requests.</p>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.35fr_0.8fr]">
        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <CardTitle>{normalized}</CardTitle>
                <div className="mt-2 text-3xl font-black tabular-nums">{ticker ? formatCurrency(ticker.lastPrice) : "-"}</div>
              </div>
              <div className={cn("rounded-md border px-3 py-2 text-sm font-bold", (ticker?.change24h ?? 0) >= 0 ? "border-success/30 bg-success/10 text-success" : "border-destructive/30 bg-destructive/10 text-destructive")}>
                {ticker ? `${ticker.change24h.toFixed(2)}% 24h` : "-"}
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-2">
              {PAIRS.map((pair) => (
                <button key={pair} onClick={() => setSymbol(pair)} className={cn("rounded-md border px-3 py-2 text-xs font-bold", normalized === pair ? "border-primary bg-primary text-primary-foreground" : "border-border bg-card text-muted-foreground hover:text-foreground")}>
                  {pair.replace("USDT", "")}
                </button>
              ))}
            </div>
            <MiniChart candles={candles} />
            <div className="grid gap-3 md:grid-cols-3">
              <Stat label="Bid" value={book ? fmt(book.bidPrice) : "-"} />
              <Stat label="Ask" value={book ? fmt(book.askPrice) : "-"} />
              <Stat label="Spread" value={book ? fmt(book.askPrice - book.bidPrice) : "-"} />
            </div>
            <div className="h-3 overflow-hidden rounded-full bg-muted">
              <div className="flex h-full">
                <div className="bg-success" style={{ flex: Math.max(1, book?.bidQty ?? 1) }} />
                <div className="bg-destructive" style={{ flex: Math.max(1, book?.askQty ?? 1) }} />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Order Request</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <Input value={symbol} onChange={(event) => setSymbol(event.target.value)} />
            <div className="grid grid-cols-2 gap-2">
              <Button variant={direction === "long" ? "default" : "outline"} className={cn(direction === "long" && "bg-success hover:bg-success/90")} onClick={() => setDirection("long")}>Long</Button>
              <Button variant={direction === "short" ? "default" : "outline"} className={cn(direction === "short" && "bg-destructive hover:bg-destructive/90")} onClick={() => setDirection("short")}>Short</Button>
            </div>
            <Input inputMode="decimal" value={entry} onChange={(event) => setEntry(event.target.value)} placeholder="Entry" />
            <Input inputMode="decimal" value={stop} onChange={(event) => setStop(event.target.value)} placeholder="Stop" />
            <Input inputMode="decimal" value={risk} onChange={(event) => setRisk(event.target.value)} placeholder="Risk %" />
            {plan ? (
              <div className="grid grid-cols-3 gap-2">
                {plan.levels.map((level, index) => <Stat key={index} label={`TP${index + 1}`} value={fmt(level)} />)}
              </div>
            ) : null}
            <Button disabled={!plan || busy} className="w-full" onClick={() => void submit()}>{busy ? "Creating..." : "Create paper order request"}</Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return <div className="rounded-md border border-border bg-card/60 p-3"><div className="text-[10px] font-bold uppercase text-muted-foreground">{label}</div><div className="mt-1 font-bold tabular-nums text-foreground">{value}</div></div>;
}

function MiniChart({ candles }: { candles: Candle[] }) {
  if (!candles.length) return <div className="grid h-64 place-items-center rounded-lg border border-border bg-background/40 text-sm text-muted-foreground">Chart loading</div>;
  const values = candles.map((item) => item.close);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 0.000001);
  return (
    <div className="flex h-64 items-end gap-1 rounded-lg border border-border bg-background/40 p-3">
      {candles.map((item, index) => (
        <div key={`${item.time}-${index}`} className={cn("flex-1 rounded-t", item.close >= item.open ? "bg-success" : "bg-destructive")} style={{ height: `${18 + ((item.close - min) / range) * 82}%` }} />
      ))}
    </div>
  );
}

async function fetchTicker(symbol: string): Promise<Ticker | null> {
  const response = await fetch(`https://api.binance.com/api/v3/ticker/24hr?symbol=${symbol}`);
  if (!response.ok) return null;
  const row = await response.json() as { lastPrice?: string; priceChangePercent?: string };
  return { lastPrice: Number(row.lastPrice ?? 0), change24h: Number(row.priceChangePercent ?? 0) };
}

async function fetchBook(symbol: string): Promise<Book | null> {
  const response = await fetch(`https://api.binance.com/api/v3/ticker/bookTicker?symbol=${symbol}`);
  if (!response.ok) return null;
  const row = await response.json() as { askPrice?: string; askQty?: string; bidPrice?: string; bidQty?: string };
  return { askPrice: Number(row.askPrice ?? 0), askQty: Number(row.askQty ?? 0), bidPrice: Number(row.bidPrice ?? 0), bidQty: Number(row.bidQty ?? 0) };
}

async function fetchCandles(symbol: string): Promise<Candle[]> {
  const response = await fetch(`https://api.binance.com/api/v3/klines?symbol=${symbol}&interval=1m&limit=48`);
  if (!response.ok) return [];
  const rows = await response.json() as unknown[][];
  return rows.map((row) => ({ time: Number(row[0]), open: Number(row[1]), close: Number(row[4]) })).filter((row) => row.close > 0);
}

function normalizeSymbol(value: string) {
  const clean = value.replace(/[^a-zA-Z0-9]/g, "").toUpperCase();
  return clean.endsWith("USDT") ? clean : `${clean}USDT`;
}

function parseNum(value: string) {
  const next = Number(value.replace(",", "."));
  return Number.isFinite(next) && next > 0 ? next : null;
}

function trim(value: number) {
  return Number(value.toFixed(8));
}

function fmt(value?: number | null) {
  if (!value) return "-";
  return value.toLocaleString("en-US", { maximumFractionDigits: value > 100 ? 2 : 6 });
}
