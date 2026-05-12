"use client";

/**
 * Aggregated queries for the decision detail page.
 *
 * The detail page needs many slices (signal that triggered the run, the
 * agent_runs row, every agent_output, the resulting trade, and lifecycle
 * events). They are fetched as separate React Query entries so React Query
 * can de-duplicate, retry, and report errors per slice without crashing the
 * page when one slice is empty or denied by RLS.
 */
import type { AgentOutput, AgentRun, Signal, Trade, TradeEvent } from "@ta/types";
import { useQuery } from "@tanstack/react-query";

import { supabase } from "../../supabase/client";

import { useCurrentUser } from "./use-current-user";

// ── Signal ───────────────────────────────────────────────────────────────────
export function useSignal(signalId: string | null | undefined) {
  return useQuery<Signal | null>({
    queryKey: ["signal", "detail", signalId],
    enabled:  !!signalId,
    queryFn: async () => {
      if (!signalId) return null;
      const { data, error } = await supabase
        .from("signals")
        .select("*")
        .eq("id", signalId)
        .maybeSingle();
      if (error) {
        console.error("decision.detail.signal.failed", { signal_id: signalId, error });
        throw error;
      }
      return (data ?? null) as Signal | null;
    },
  });
}

// ── Agent runs for a decision ────────────────────────────────────────────────
export function useDecisionAgentRuns(
  decisionId: string | null | undefined,
  fallbackAgentRunId?: string | null,
) {
  return useQuery<AgentRun[]>({
    queryKey: ["decisions", "agent-runs", decisionId, fallbackAgentRunId ?? null],
    enabled:  !!decisionId || !!fallbackAgentRunId,
    queryFn: async () => {
      // Prefer trade_decision_id linkage; fall back to the explicit id from
      // the trade_decisions row (covers older schemas where the back-link
      // is not populated).
      let q = supabase.from("agent_runs").select("*");
      if (decisionId)            q = q.eq("trade_decision_id", decisionId);
      else if (fallbackAgentRunId) q = q.eq("id", fallbackAgentRunId);

      const { data, error } = await q.order("started_at", { ascending: true });
      if (error) {
        console.error("decision.detail.agent_runs.failed", {
          decision_id: decisionId, agent_run_id: fallbackAgentRunId, error,
        });
        throw error;
      }
      return (data ?? []) as AgentRun[];
    },
  });
}

// ── Agent outputs for an agent run ───────────────────────────────────────────
export function useAgentOutputs(agentRunId: string | null | undefined) {
  return useQuery<AgentOutput[]>({
    queryKey: ["agent-runs", "outputs", agentRunId],
    enabled:  !!agentRunId,
    queryFn: async () => {
      if (!agentRunId) return [];
      const { data, error } = await supabase
        .from("agent_outputs")
        .select("*")
        .eq("agent_run_id", agentRunId)
        .order("created_at", { ascending: true });
      if (error) {
        console.error("decision.detail.agent_outputs.failed", { agent_run_id: agentRunId, error });
        throw error;
      }
      return (data ?? []) as AgentOutput[];
    },
  });
}

// ── Trade resulting from a decision ──────────────────────────────────────────
export function useTradeForDecision(decisionId: string | null | undefined) {
  return useQuery<Trade | null>({
    queryKey: ["decisions", "trade", decisionId],
    enabled:  !!decisionId,
    queryFn: async () => {
      if (!decisionId) return null;
      const { data, error } = await supabase
        .from("trades")
        .select("*")
        .eq("trade_decision_id", decisionId)
        .order("created_at", { ascending: false })
        .limit(1)
        .maybeSingle();
      if (error) {
        console.error("decision.detail.trade.failed", { decision_id: decisionId, error });
        throw error;
      }
      return (data ?? null) as Trade | null;
    },
  });
}

// ── Lifecycle events linked to the decision ──────────────────────────────────
export function useTradeEventsForDecision(decisionId: string | null | undefined) {
  return useQuery<TradeEvent[]>({
    queryKey: ["decisions", "trade-events", decisionId],
    enabled:  !!decisionId,
    queryFn: async () => {
      if (!decisionId) return [];
      const { data, error } = await supabase
        .from("trade_events")
        .select("id, trade_id, trade_decision_id, bot_id, user_id, event_type, metadata, created_at")
        .eq("trade_decision_id", decisionId)
        .order("created_at", { ascending: true });
      if (error) {
        console.error("decision.detail.trade_events.failed", { decision_id: decisionId, error });
        throw error;
      }
      return (data ?? []) as TradeEvent[];
    },
  });
}

// Re-exports for convenience inside the detail page
export { useDecision } from "./use-decisions";
export { useCurrentUser };
