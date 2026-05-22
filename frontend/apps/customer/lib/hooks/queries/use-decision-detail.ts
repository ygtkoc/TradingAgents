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
import { enrichLivePnl } from "./use-trades";

function normalizeTradeEvent(row: TradeEvent): TradeEvent {
  const details = (row.details ?? row.metadata ?? {}) as Record<string, unknown>;
  return { ...row, details, metadata: (row.metadata ?? details) as Record<string, unknown> };
}

function normalizeAgentOutput(row: Record<string, unknown>): AgentOutput {
  const output = (row.output as Record<string, unknown> | null) ?? {};
  const definition = (row.agent_definitions as Record<string, unknown> | null) ?? {};
  const agentName =
    typeof row.agent_name === "string" ? row.agent_name
    : typeof output.agent_name === "string" ? output.agent_name
    : typeof definition.name === "string" ? definition.name
    : typeof definition.display_name === "string" ? definition.display_name
    : "unknown_agent";
  return {
    ...(row as unknown as AgentOutput),
    agent_name: agentName,
    agent_display_name: typeof definition.display_name === "string"
      ? definition.display_name
      : agentName,
    decision: typeof row.decision === "string"
      ? row.decision
      : typeof output.decision === "string"
        ? output.decision
        : null,
    score: typeof row.score === "number"
      ? row.score
      : typeof output.score === "number"
        ? output.score
        : null,
    confidence: typeof row.confidence === "number"
      ? row.confidence
      : typeof output.confidence === "number"
        ? output.confidence
        : null,
    veto: typeof row.veto === "boolean"
      ? row.veto
      : typeof output.veto === "boolean"
        ? output.veto
        : null,
    reasoning: typeof row.reasoning === "string"
      ? row.reasoning
      : typeof output.reasoning === "string"
        ? output.reasoning
        : null,
    output,
  };
}

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
      if (decisionId) q = q.eq("trade_decision_id", decisionId);
      else if (fallbackAgentRunId) q = q.eq("id", fallbackAgentRunId);

      let { data, error } = await q.order("started_at", { ascending: true });
      if (error) {
        console.error("decision.detail.agent_runs.failed", {
          decision_id: decisionId, agent_run_id: fallbackAgentRunId, error,
        });
        throw error;
      }

      if ((!data || data.length === 0) && fallbackAgentRunId) {
        const fallback = await supabase
          .from("agent_runs")
          .select("*")
          .eq("id", fallbackAgentRunId)
          .limit(1);
        if (fallback.error) {
          console.error("decision.detail.agent_run_fallback.failed", {
            decision_id: decisionId, agent_run_id: fallbackAgentRunId, error: fallback.error,
          });
          throw fallback.error;
        }
        data = fallback.data;
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
        .select("*, agent_definitions(name, display_name)")
        .eq("agent_run_id", agentRunId)
        .order("created_at", { ascending: true });
      if (error) {
        console.error("decision.detail.agent_outputs.failed", { agent_run_id: agentRunId, error });
        throw error;
      }
      return ((data ?? []) as Record<string, unknown>[]).map(normalizeAgentOutput);
    },
  });
}

// ── Trade resulting from a decision ──────────────────────────────────────────
export function useTradeForDecision(decisionId: string | null | undefined) {
  return useQuery<Trade | null>({
    queryKey: ["decisions", "trade", decisionId],
    enabled:  !!decisionId,
    staleTime: 0,
    refetchInterval: 5_000,
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
      const row = (data ?? null) as Trade | null;
      if (!row) return null;
      return (await enrichLivePnl([row]))[0] ?? row;
    },
  });
}

// ── Lifecycle events linked to the decision ──────────────────────────────────
export function useTradeEventsForDecision(decisionId: string | null | undefined) {
  return useQuery<TradeEvent[]>({
    queryKey: ["decisions", "trade-events", decisionId],
    enabled:  !!decisionId,
    staleTime: 0,
    refetchInterval: 5_000,
    queryFn: async () => {
      if (!decisionId) return [];
      const { data, error } = await supabase
        .from("trade_events")
        .select("*")
        .eq("trade_decision_id", decisionId)
        .order("created_at", { ascending: true });
      if (error) {
        console.error("decision.detail.trade_events.failed", { decision_id: decisionId, error });
        throw error;
      }
      return ((data ?? []) as TradeEvent[]).map(normalizeTradeEvent);
    },
  });
}

// Re-exports for convenience inside the detail page
export { useDecision } from "./use-decisions";
export { useCurrentUser };
