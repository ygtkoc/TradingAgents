"use client";

import { useMemo } from "react";

import { useBots } from "./use-bots";
import { isFilledPosition, useTrades } from "./use-trades";
import { useDecisions } from "./use-decisions";
import { useRiskLogs } from "./use-logs";

/**
 * Aggregates a few read queries into the KPI tiles for the dashboard.
 * Pure client-side aggregation — backend remains the source of truth.
 */
export function useDashboardKpis() {
  const bots      = useBots();
  const trades    = useTrades({ limit: 200 });
  const decisions = useDecisions({ approval: "pending", limit: 100 });
  const risk      = useRiskLogs({ limit: 100 });

  const isLoading = bots.isLoading || trades.isLoading || decisions.isLoading;
  const isError   = bots.isError   || trades.isError   || decisions.isError;

  const kpis = useMemo(() => {
    const tradesData = trades.data ?? [];
    const open  = tradesData.filter(isFilledPosition);
    const realised = tradesData.reduce((s, t) => s + (t.realized_pnl ?? 0), 0);
    const unreal   = open.reduce((s, t) => s + (t.unrealized_pnl ?? 0), 0);
    const activeBots = (bots.data ?? []).filter((b) => b.status === "active").length;
    const pendingDecisions = decisions.data?.length ?? 0;
    const triggeredHigh = (risk.data ?? []).filter(
      (r) => r.triggered && (r.severity === "high" || r.severity === "critical"),
    ).length;

    return {
      totalPnl:          realised + unreal,
      openTradesCount:   open.length,
      activeBotsCount:   activeBots,
      pendingDecisions,
      riskAlerts:        triggeredHigh,
    };
  }, [bots.data, trades.data, decisions.data, risk.data]);

  return { ...kpis, isLoading, isError };
}
