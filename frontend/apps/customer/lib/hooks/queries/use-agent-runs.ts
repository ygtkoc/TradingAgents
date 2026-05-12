"use client";

import { queryKeys } from "@ta/query/keys";
import type { AgentOutput, AgentRun } from "@ta/types";
import { useQuery } from "@tanstack/react-query";

import { supabase } from "../../supabase/client";

function normalizeAgentRun(row: Record<string, unknown>): AgentRun {
  return {
    id: String(row.id ?? ""),
    user_id: String(row.user_id ?? ""),
    bot_id: String(row.bot_id ?? ""),
    signal_id: typeof row.signal_id === "string" ? row.signal_id : null,
    status: typeof row.run_status === "string"
      ? row.run_status as AgentRun["status"]
      : typeof row.status === "string"
        ? row.status as AgentRun["status"]
        : "running",
    started_at: String(row.started_at ?? ""),
    completed_at: typeof row.completed_at === "string" ? row.completed_at : null,
    final_decision: typeof row.final_decision === "string" ? row.final_decision as AgentRun["final_decision"] : null,
    total_cost_usd: typeof row.total_cost_usd === "number" ? row.total_cost_usd : null,
    total_tokens: typeof row.total_tokens === "number" ? row.total_tokens : null,
    metadata: (row.metadata as Record<string, unknown>) ?? {},
    trade_decision_id: typeof row.trade_decision_id === "string" ? row.trade_decision_id : null,
    error_message: typeof row.error_message === "string" ? row.error_message : null,
    duration_ms: typeof row.duration_ms === "number" ? row.duration_ms : null,
  };
}

export function useAgentRuns(opts: { botId?: string; signalId?: string; limit?: number } = {}) {
  return useQuery<AgentRun[]>({
    queryKey: queryKeys.agentRuns.list(opts),
    queryFn: async () => {
      let q = supabase.from("agent_runs").select("*").order("started_at", { ascending: false });
      if (opts.botId) q = q.eq("bot_id", opts.botId);
      if (opts.signalId) q = q.eq("signal_id", opts.signalId);
      q = q.limit(opts.limit ?? 50);
      const { data, error } = await q;
      if (error) throw error;
      return ((data ?? []) as Record<string, unknown>[]).map(normalizeAgentRun);
    },
  });
}

export function useAgentRun(runId: string | undefined) {
  return useQuery<AgentRun | null>({
    queryKey: runId ? queryKeys.agentRuns.detail(runId) : ["agent-runs", "detail", "none"],
    enabled: !!runId,
    queryFn: async () => {
      if (!runId) return null;
      const { data, error } = await supabase
        .from("agent_runs")
        .select("*")
        .eq("id", runId)
        .maybeSingle();
      if (error) throw error;
      return data ? normalizeAgentRun(data as Record<string, unknown>) : null;
    },
  });
}

export function useAgentOutputs(runId: string | undefined) {
  return useQuery<AgentOutput[]>({
    queryKey: runId ? queryKeys.agentRuns.outputs(runId) : ["agent-runs", "outputs", "none"],
    enabled: !!runId,
    queryFn: async () => {
      if (!runId) return [];
      const { data, error } = await supabase
        .from("agent_outputs")
        .select("*")
        .eq("agent_run_id", runId)
        .order("created_at", { ascending: true });
      if (error) throw error;
      return (data ?? []) as AgentOutput[];
    },
  });
}
