"use client";

import { queryKeys } from "@ta/query/keys";
import type { TradeEvent } from "@ta/types";
import { useQuery } from "@tanstack/react-query";

import { supabase } from "../../supabase/client";

export function useTradeEvents(tradeId: string | undefined) {
  return useQuery<TradeEvent[]>({
    queryKey: tradeId ? queryKeys.trades.events(tradeId) : ["trades", "events", "none"],
    enabled:  !!tradeId,
    staleTime: 0,
    refetchInterval: 5_000,
    queryFn: async () => {
      if (!tradeId) return [];
      const { data, error } = await supabase
        .from("trade_events")
        .select("*")
        .eq("trade_id", tradeId)
        .order("created_at", { ascending: true });
      if (error) throw error;
      return (data ?? []) as TradeEvent[];
    },
  });
}

export function useTradeDecisionEvents(tradeDecisionId: string | undefined) {
  return useQuery<TradeEvent[]>({
    queryKey: tradeDecisionId ? ["trade-decisions", "events", tradeDecisionId] : ["trade-decisions", "events", "none"],
    enabled: !!tradeDecisionId,
    staleTime: 0,
    refetchInterval: 5_000,
    queryFn: async () => {
      if (!tradeDecisionId) return [];
      const { data, error } = await supabase
        .from("trade_events")
        .select("*")
        .eq("trade_decision_id", tradeDecisionId)
        .order("created_at", { ascending: true });
      if (error) throw error;
      return (data ?? []) as TradeEvent[];
    },
  });
}
