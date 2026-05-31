"use client";

import { queryKeys } from "@ta/query/keys";
import type { Trade } from "@ta/types";
import { useQuery } from "@tanstack/react-query";

import { demoTrades } from "../../demo/demo-trades";
import { isDemoMode, withDemoFallback } from "../../demo";
import { supabase } from "../../supabase/client";

import { useCurrentUser } from "./use-current-user";

export interface TradeFilters {
  status?: Trade["status"];
  /** Multi-status filter (e.g. ["pending","failed","cancelled"]). Ignored when `status` is set. */
  statuses?: Array<Trade["status"]>;
  mode?:   "paper" | "live" | "shadow";
  botId?:  string;
  limit?:  number;
  enabled?: boolean;
}

function applyFilters(rows: Trade[], f: TradeFilters): Trade[] {
  let out = rows;
  if (f.status) out = out.filter((t) => t.status === f.status);
  else if (f.statuses && f.statuses.length > 0) out = out.filter((t) => f.statuses!.includes(t.status));
  if (f.status === "open") out = out.filter(isFilledPosition);
  if (f.mode)   out = out.filter((t) => t.mode === f.mode);
  if (f.botId)  out = out.filter((t) => t.bot_id === f.botId);
  if (f.limit)  out = out.slice(0, f.limit);
  return out;
}

export function isFilledPosition(trade: Trade): boolean {
  const filledQty = Number(trade.filled_quantity ?? 0);
  const avgFill   = Number(trade.avg_fill_price ?? trade.avg_entry_price ?? 0);
  const hasFill   =
    filledQty > 0 ||
    Number.isFinite(avgFill) && avgFill > 0 ||
    trade.metadata?.paper_fill_status === "filled";

  return trade.status === "open" && hasFill;
}

function isPriceTrackable(trade: Trade): boolean {
  // Shadow mode stores intended orders as status="simulated" but still has fill
  // data (filled_quantity + avg_fill_price). Treat these as position-like for
  // live P&L display.
  if (trade.status !== "open" && trade.status !== "simulated") return false;
  const filledQty = Number(trade.filled_quantity ?? 0);
  const avgFill   = Number(trade.avg_fill_price ?? trade.avg_entry_price ?? 0);
  return (
    filledQty > 0 ||
    (Number.isFinite(avgFill) && avgFill > 0) ||
    trade.metadata?.paper_fill_status === "filled"
  );
}

function toNum(value: unknown): number | null {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function normalizeSymbol(symbol: string): string {
  return symbol.replace("/", "").toUpperCase();
}

function calcPnl(trade: Trade, currentPrice: number): { pnl: number; pnl_pct: number } | null {
  const entry = toNum(trade.avg_fill_price ?? trade.avg_entry_price ?? trade.entry_price);
  const qty   = toNum(trade.filled_quantity) ?? toNum(trade.quantity);
  if (entry == null || qty == null || currentPrice == null) return null;
  if (entry <= 0 || qty <= 0 || currentPrice <= 0) return null;
  const raw = trade.direction === "short"
    ? (entry - currentPrice) * qty
    : (currentPrice - entry) * qty;
  return { pnl: raw, pnl_pct: (raw / (entry * qty)) * 100 };
}

async function latestBinancePrices(symbols: string[]): Promise<Map<string, number>> {
  const normalized = Array.from(new Set(symbols.map(normalizeSymbol))).filter(Boolean);
  if (normalized.length === 0) return new Map();

  const settled = await Promise.allSettled(normalized.map(async (symbol) => {
    const url = `https://api.binance.com/api/v3/ticker/price?symbol=${encodeURIComponent(symbol)}`;
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error(`Binance ticker failed for ${symbol}: ${response.status}`);
    const row = (await response.json()) as { symbol?: string; price?: string };
    const price = toNum(row.price);
    return price != null && price > 0 ? [symbol, price] as const : null;
  }));

  const prices = new Map<string, number>();
  for (const item of settled) {
    if (item.status === "fulfilled" && item.value) {
      prices.set(item.value[0], item.value[1]);
    }
  }
  return prices;
}

async function latestSnapshotPrices(symbols: string[]): Promise<Map<string, number>> {
  if (symbols.length === 0) return new Map();

  const { data, error } = await supabase
    .from("market_snapshots")
    .select("symbol, close_price, captured_at")
    .in("symbol", symbols)
    .eq("timeframe", "1m")
    .order("captured_at", { ascending: false })
    .limit(Math.max(20, symbols.length * 8));

  if (error) {
    console.error("trades.latest_prices.failed", { symbols, error });
    return new Map();
  }

  const out = new Map<string, number>();
  for (const row of data ?? []) {
    const symbol = String((row as Record<string, unknown>).symbol ?? "");
    if (out.has(symbol)) continue;
    const price = toNum((row as Record<string, unknown>).close_price);
    if (price != null && price > 0) out.set(symbol, price);
  }
  return out;
}

async function latestPricesForTrades(rows: Trade[]): Promise<Map<string, number>> {
  const symbols = Array.from(new Set(rows.filter(isPriceTrackable).map((t) => t.symbol)));
  if (symbols.length === 0) return new Map();

  const prices = await latestBinancePrices(symbols);
  if (prices.size === symbols.length) return prices;

  const snapshots = await latestSnapshotPrices(symbols);
  for (const [symbol, price] of snapshots) {
    if (!prices.has(symbol)) prices.set(symbol, price);
    const normalized = normalizeSymbol(symbol);
    if (!prices.has(normalized)) prices.set(normalized, price);
  }
  return prices;
}

export async function enrichLivePnl(rows: Trade[]): Promise<Trade[]> {
  const normalized = rows.map((trade) => ({
    ...trade,
    avg_fill_price: trade.avg_fill_price ?? trade.avg_entry_price ?? null,
  }));
  const prices = await latestPricesForTrades(normalized);
  if (prices.size === 0) return normalized;

  return normalized.map((trade) => {
    if (!isPriceTrackable(trade)) return trade;
    const price = prices.get(normalizeSymbol(trade.symbol)) ?? prices.get(trade.symbol);
    if (!price) return trade;
    const computed = calcPnl(trade, price);
    if (!computed) return trade;
    return {
      ...trade,
      unrealized_pnl: computed.pnl,
      pnl: computed.pnl,
      pnl_pct: computed.pnl_pct,
      metadata: { ...(trade.metadata ?? {}), latest_price: price },
    };
  });
}

export function useTrades(filters: TradeFilters = {}) {
  const { data: user } = useCurrentUser();
  return useQuery<Trade[]>({
    queryKey: queryKeys.trades.list({ ...filters, userId: user?.id }),
    enabled:  !!user && (filters.enabled ?? true),
    staleTime: 0,
    refetchInterval: 1_000,
    refetchIntervalInBackground: true,
    queryFn: async () => {
      if (isDemoMode) return applyFilters(demoTrades, filters);
      let q = supabase
        .from("trades")
        .select("*")
        .eq("user_id", user!.id)
        .order("created_at", { ascending: false });
      if (filters.status) {
        q = q.eq("status", filters.status);
      } else if (filters.statuses && filters.statuses.length > 0) {
        q = q.in("status", filters.statuses);
      }
      if (filters.mode)   q = q.eq("mode",   filters.mode);
      if (filters.botId)  q = q.eq("bot_id", filters.botId);
      if (filters.limit)  q = q.limit(filters.limit);
      const { data, error } = await q;
      if (error) {
        console.error("paper.trades.query.failed", {
          user_id: user?.id,
          filters,
          error,
        });
        console.error("dashboard.trades.load.failed", {
          user_id: user?.id,
          filters,
          error,
        });
        throw error;
      }
      const rows = withDemoFallback((data ?? []) as Trade[], applyFilters(demoTrades, filters));
      return enrichLivePnl(rows);
    },
  });
}

export function useOpenTrades() {
  const { data: user } = useCurrentUser();
  return useQuery<Trade[]>({
    queryKey: queryKeys.trades.open(user?.id),
    enabled:  !!user,
    staleTime: 0,
    refetchInterval: 1_000,
    refetchIntervalInBackground: true,
    queryFn: async () => {
      if (isDemoMode) return demoTrades.filter(isFilledPosition);
      const { data, error } = await supabase
        .from("trades")
        .select("*")
        .eq("user_id", user!.id)
        .eq("status", "open")
        .order("created_at", { ascending: false });
      if (error) throw error;
      return withDemoFallback(
        await enrichLivePnl((data ?? []) as Trade[]),
        demoTrades.filter(isFilledPosition),
      );
    },
  });
}

export function useTrade(tradeId: string | undefined) {
  const { data: user } = useCurrentUser();
  return useQuery<Trade | null>({
    queryKey: tradeId ? queryKeys.trades.detail(tradeId) : ["trades", "detail", "none"],
    enabled:  !!tradeId && !!user,
    staleTime: 0,
    refetchInterval: 1_000,
    refetchIntervalInBackground: true,
    queryFn: async () => {
      if (!tradeId) return null;
      if (isDemoMode) {
        return demoTrades.find((t) => t.id === tradeId) ?? demoTrades[0] ?? null;
      }
      const { data, error } = await supabase
        .from("trades")
        .select("*")
        .eq("user_id", user!.id)
        .eq("id", tradeId)
        .maybeSingle();
      if (error) throw error;
      const row = (data ?? null) as Trade | null;
      if (!row) return null;
      return (await enrichLivePnl([row]))[0] ?? row;
    },
  });
}
