import { demoTrades } from "./demo-trades";
import { demoBots }   from "./demo-bots";
import { demoDecisions } from "./demo-decisions";

/**
 * Pre-aggregated demo KPI snapshot. Mirrors the shape produced by
 * useDashboardKpis so demo paths can return identical structure.
 */
export const demoKpis = {
  totalPnl:
    demoTrades.reduce((s, t) => s + (t.realized_pnl ?? 0), 0) +
    demoTrades.filter((t) => t.status === "open").reduce((s, t) => s + (t.unrealized_pnl ?? 0), 0),
  openTradesCount:  demoTrades.filter((t) => t.status === "open").length,
  activeBotsCount:  demoBots.filter((b) => b.status === "active").length,
  pendingDecisions: demoDecisions.filter((d) => d.approval_status === "pending").length,
  riskAlerts:       1,
};
