"use client";

import { KpiCard } from "@ta/ui";
import { formatCurrency } from "@ta/utils";

import { useDashboardKpis } from "@/lib/hooks/queries/use-dashboard-kpis";

export function DashboardKpis() {
  const k = useDashboardKpis();

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
      <KpiCard
        label="Total P&L"
        loading={k.isLoading}
        value={formatCurrency(k.totalPnl)}
        trend={k.totalPnl > 0 ? "up" : k.totalPnl < 0 ? "down" : "flat"}
      />
      <KpiCard
        label="Open Trades"
        loading={k.isLoading}
        value={k.openTradesCount}
      />
      <KpiCard
        label="Active Bots"
        loading={k.isLoading}
        value={k.activeBotsCount}
      />
      <KpiCard
        label="Pending Decisions"
        loading={k.isLoading}
        value={k.pendingDecisions}
        hint={k.pendingDecisions > 0 ? "Awaiting your approval" : undefined}
      />
      <KpiCard
        label="Risk Alerts"
        loading={k.isLoading}
        value={k.riskAlerts}
        trend={k.riskAlerts > 0 ? "down" : "flat"}
        hint={k.riskAlerts > 0 ? "High/critical in last 100" : "All clear"}
      />
    </div>
  );
}
