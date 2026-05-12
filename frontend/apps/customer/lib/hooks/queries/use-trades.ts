"use client";

import { queryKeys } from "@ta/query/keys";
import type { Trade } from "@ta/types";
import { useQuery } from "@tanstack/react-query";

import { demoTrades } from "../../demo/demo-trades";
import { isDemoMode, withDemoFallback } from "../../demo";
import { supabase } from "../../supabase/client";

import { useCurrentUser } from "./use-current-user";

export interface TradeFilters {
  status?: "open" | "closed";
  mode?:   "paper" | "live" | "shadow";
  botId?:  string;
  limit?:  number;
  enabled?: boolean;
}

function applyFilters(rows: Trade[], f: TradeFilters): Trade[] {
  let out = rows;
  if (f.status) out = out.filter((t) => t.status === f.status);
  if (f.mode)   out = out.filter((t) => t.mode === f.mode);
  if (f.botId)  out = out.filter((t) => t.bot_id === f.botId);
  if (f.limit)  out = out.slice(0, f.limit);
  return out;
}

export function useTrades(filters: TradeFilters = {}) {
  const { data: user } = useCurrentUser();
  return useQuery<Trade[]>({
    queryKey: queryKeys.trades.list({ ...filters, userId: user?.id }),
    enabled:  !!user && (filters.enabled ?? true),
    staleTime: 0,
    refetchInterval: 5_000,
    queryFn: async () => {
      if (isDemoMode) return applyFilters(demoTrades, filters);
      let q = supabase.from("trades").select("*").order("created_at", { ascending: false });
      if (filters.status) q = q.eq("status", filters.status);
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
      return rows;
    },
  });
}

export function useOpenTrades() {
  const { data: user } = useCurrentUser();
  return useQuery<Trade[]>({
    queryKey: queryKeys.trades.open(user?.id),
    enabled:  !!user,
    staleTime: 0,
    refetchInterval: 5_000,
    queryFn: async () => {
      if (isDemoMode) return demoTrades.filter((t) => t.status === "open");
      const { data, error } = await supabase
        .from("trades")
        .select("*")
        .eq("status", "open")
        .order("created_at", { ascending: false });
      if (error) throw error;
      return withDemoFallback(
        (data ?? []) as Trade[],
        demoTrades.filter((t) => t.status === "open"),
      );
    },
  });
}

export function useTrade(tradeId: string | undefined) {
  return useQuery<Trade | null>({
    queryKey: tradeId ? queryKeys.trades.detail(tradeId) : ["trades", "detail", "none"],
    enabled:  !!tradeId,
    queryFn: async () => {
      if (!tradeId) return null;
      if (isDemoMode) {
        return demoTrades.find((t) => t.id === tradeId) ?? demoTrades[0] ?? null;
      }
      const { data, error } = await supabase
        .from("trades")
        .select("*")
        .eq("id", tradeId)
        .maybeSingle();
      if (error) throw error;
      return (data ?? null) as Trade | null;
    },
  });
}
