"use client";

import { useQuery } from "@tanstack/react-query";

import { supabase } from "../../supabase/client";
import { useCurrentUser } from "./use-current-user";

export interface PaperAccount {
  id:                string;
  user_id:           string;
  currency:          string;
  starting_balance:  number;
  balance:           number;
  realized_pnl:      number;
  unrealized_pnl:    number;
  equity:            number;
  status:            "inactive" | "active" | "paused";
  is_active:         boolean;
  started_at:        string | null;
  paused_at:         string | null;
  reset_at:          string | null;
  created_at:        string;
  updated_at:        string | null;
  metadata:          Record<string, unknown>;
}

function normalizePaperAccount(row: Record<string, unknown>): PaperAccount {
  const rawStatus = typeof row.status === "string" ? row.status : row.is_active ? "active" : "inactive";
  const status: PaperAccount["status"] =
    rawStatus === "active" || rawStatus === "paused" || rawStatus === "inactive"
      ? rawStatus
      : "inactive";

  return {
    id: String(row.id ?? ""),
    user_id: String(row.user_id ?? ""),
    currency: typeof row.currency === "string" ? row.currency : "USD",
    starting_balance: Number(row.starting_balance ?? 0),
    balance: Number(row.balance ?? 0),
    realized_pnl: Number(row.realized_pnl ?? 0),
    unrealized_pnl: Number(row.unrealized_pnl ?? 0),
    equity: Number(row.equity ?? row.balance ?? 0),
    status,
    is_active: Boolean(row.is_active ?? status === "active"),
    started_at: typeof row.started_at === "string" ? row.started_at : null,
    paused_at: typeof row.paused_at === "string" ? row.paused_at : null,
    reset_at: typeof row.reset_at === "string" ? row.reset_at : null,
    created_at: String(row.created_at ?? ""),
    updated_at: typeof row.updated_at === "string" ? row.updated_at : null,
    metadata: (row.metadata as Record<string, unknown>) ?? {},
  };
}

export function usePaperAccount() {
  const { data: user } = useCurrentUser();
  return useQuery<PaperAccount | null>({
    queryKey: ["paper-account", user?.id],
    enabled:  !!user,
    staleTime: 0,
    refetchInterval: 5_000,   // Poll every 5 s — shows balance/PnL changes live
    queryFn: async () => {
      console.info("paper_account.load.start", { user_id: user!.id });
      try {
        const { data, error } = await supabase
          .from("paper_accounts")
          .select("*")
          .eq("user_id", user!.id)
          .maybeSingle();
        if (error) throw error;
        if (!data) {
          console.info("paper_account.load.empty", { user_id: user!.id });
        }
        return data ? normalizePaperAccount(data as Record<string, unknown>) : null;
      } catch (error) {
        console.error("paper.account.query.failed", {
          user_id: user!.id,
          error,
        });
        console.error("paper_account.load.failed", {
          user_id: user!.id,
          error,
        });
        throw error;
      }
    },
  });
}

export interface PaperAccountEvent {
  id:               string;
  trade_id:         string | null;
  event_type:       string;
  delta:            number;
  realized_delta:   number;
  unrealized_delta: number;
  balance_after:    number;
  realized_after:   number;
  unrealized_after?: number | null;
  note:             string | null;
  metadata?:         Record<string, unknown> | null;
  created_at:       string;
  trades?: {
    symbol?: string | null;
    direction?: string | null;
    status?: string | null;
    entry_price?: number | null;
    exit_price?: number | null;
    realized_pnl?: number | null;
    pnl_pct?: number | null;
    close_reason?: string | null;
  } | null;
}

export function usePaperAccountEvents(limit = 50, enabled = true) {
  const { data: user } = useCurrentUser();
  return useQuery<PaperAccountEvent[]>({
    queryKey: ["paper-account-events", user?.id, limit],
    enabled:  !!user && enabled,
    staleTime: 0,
    refetchInterval: 5_000,
    queryFn: async () => {
      try {
        const { data, error } = await supabase
          .from("paper_account_events")
          .select(`
            *,
            trades (
              symbol,
              direction,
              status,
              entry_price,
              exit_price,
              realized_pnl,
              pnl_pct,
              close_reason
            )
          `)
          .eq("user_id", user!.id)
          .order("created_at", { ascending: false })
          .limit(limit);
        if (error) throw error;
        return (data ?? []) as PaperAccountEvent[];
      } catch (error) {
        console.error("paper.positions.query.failed", {
          user_id: user!.id,
          limit,
          error,
        });
        throw error;
      }
    },
  });
}
