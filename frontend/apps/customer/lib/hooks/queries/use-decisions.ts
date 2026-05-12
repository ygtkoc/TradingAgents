"use client";

import { queryKeys } from "@ta/query/keys";
import type { TradeDecision } from "@ta/types";
import { useQuery } from "@tanstack/react-query";

import { demoDecisions } from "../../demo/demo-decisions";
import { isDemoMode, withDemoFallback } from "../../demo";
import { supabase } from "../../supabase/client";

import { useCurrentUser } from "./use-current-user";

export interface DecisionFilters {
  approval?: "pending" | "approved" | "auto_approved" | "rejected" | "manual_review";
  botId?:    string;
  limit?:    number;
  enabled?:  boolean;
}

function applyFilters(rows: TradeDecision[], f: DecisionFilters): TradeDecision[] {
  let out = rows;
  if (f.approval) out = out.filter((d) => d.approval_status === f.approval);
  if (f.botId)    out = out.filter((d) => d.bot_id === f.botId);
  if (f.limit)    out = out.slice(0, f.limit);
  return out;
}

export function useDecisions(filters: DecisionFilters = {}) {
  const { data: user } = useCurrentUser();
  return useQuery<TradeDecision[]>({
    queryKey: queryKeys.decisions.list({ ...filters, userId: user?.id }),
    enabled:  !!user && (filters.enabled ?? true),
    staleTime: 0,
    refetchInterval: 5_000,
    queryFn: async () => {
      if (isDemoMode) return applyFilters(demoDecisions, filters);
      let q = supabase.from("trade_decisions").select("*").order("created_at", { ascending: false });
      if (filters.approval) q = q.eq("approval_status", filters.approval);
      if (filters.botId)    q = q.eq("bot_id", filters.botId);
      if (filters.limit)    q = q.limit(filters.limit);
      const { data, error } = await q;
      if (error) {
        console.error("paper.decisions.query.failed", {
          user_id: user?.id,
          filters,
          error,
        });
        console.error("dashboard.decisions.load.failed", {
          user_id: user?.id,
          filters,
          error,
        });
        throw error;
      }
      return withDemoFallback(
        (data ?? []) as TradeDecision[],
        applyFilters(demoDecisions, filters),
      );
    },
  });
}

export function useDecision(id: string | undefined) {
  const { data: user } = useCurrentUser();
  return useQuery<TradeDecision | null>({
    queryKey: id ? queryKeys.decisions.detail(id) : ["decisions", "detail", "none"],
    enabled: !!user && !!id,
    queryFn: async () => {
      if (!id) return null;
      if (isDemoMode) {
        return demoDecisions.find((decision) => decision.id === id) ?? null;
      }
      const { data, error } = await supabase
        .from("trade_decisions")
        .select("*")
        .eq("id", id)
        .maybeSingle();
      if (error) {
        console.error("dashboard.decision.load.failed", {
          user_id: user?.id,
          decision_id: id,
          error,
        });
        throw error;
      }
      return (data ?? null) as TradeDecision | null;
    },
  });
}

export function usePendingDecisions() {
  const { data: user } = useCurrentUser();
  return useQuery<TradeDecision[]>({
    queryKey: queryKeys.decisions.pendingApproval(user?.id),
    enabled:  !!user,
    staleTime: 0,
    refetchInterval: 5_000,
    queryFn: async () => {
      if (isDemoMode) return demoDecisions.filter((d) => d.approval_status === "pending");
      const { data, error } = await supabase
        .from("trade_decisions")
        .select("*")
        .eq("approval_status", "pending")
        .order("created_at", { ascending: false });
      if (error) throw error;
      return withDemoFallback(
        (data ?? []) as TradeDecision[],
        demoDecisions.filter((d) => d.approval_status === "pending"),
      );
    },
  });
}
