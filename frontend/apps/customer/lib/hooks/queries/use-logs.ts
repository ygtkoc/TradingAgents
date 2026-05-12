"use client";

import { queryKeys } from "@ta/query/keys";
import type { RiskLog, SecurityLog, AuditLog } from "@ta/types";
import { useQuery } from "@tanstack/react-query";

import { supabase } from "../../supabase/client";

export function useRiskLogs(opts: { tradeId?: string; botId?: string; limit?: number } = {}) {
  return useQuery<RiskLog[]>({
    queryKey: queryKeys.logs.risk(opts),
    queryFn: async () => {
      let q = supabase.from("risk_logs").select("*").order("created_at", { ascending: false });
      if (opts.tradeId) q = q.eq("trade_id", opts.tradeId);
      if (opts.botId)   q = q.eq("bot_id",   opts.botId);
      q = q.limit(opts.limit ?? 50);
      const { data, error } = await q;
      if (error) throw error;
      return (data ?? []) as RiskLog[];
    },
  });
}

export function useSecurityLogs(opts: { limit?: number } = {}) {
  return useQuery<SecurityLog[]>({
    queryKey: queryKeys.logs.security(opts),
    queryFn: async () => {
      const { data, error } = await supabase
        .from("security_logs")
        .select("*")
        .order("created_at", { ascending: false })
        .limit(opts.limit ?? 50);
      if (error) throw error;
      return (data ?? []) as SecurityLog[];
    },
  });
}

export function useAuditLogs(opts: { recordId?: string; limit?: number } = {}) {
  return useQuery<AuditLog[]>({
    queryKey: queryKeys.logs.audit(opts),
    queryFn: async () => {
      let q = supabase.from("audit_logs").select("*").order("created_at", { ascending: false });
      if (opts.recordId) q = q.eq("record_id", opts.recordId);
      q = q.limit(opts.limit ?? 50);
      const { data, error } = await q;
      if (error) throw error;
      return (data ?? []) as AuditLog[];
    },
  });
}
