"use client";

import { IntelligenceCard, PageHeader, ProductPage } from "@ta/ui";

import { TradesTable } from "@/components/trades/trades-table";

export default function TradesPage() {
  return (
    <ProductPage size="xl">
      <PageHeader
        eyebrow="Position engine"
        title="Trades and position health"
        description="Inspect every paper, shadow, and live-gated position with P&L, R-multiple, lifecycle state, and execution status."
      />
      <div className="grid gap-3 md:grid-cols-3">
        <IntelligenceCard title="Lifecycle" value="Tracked" label="pending, open, closed, failed, simulated" tone="blue" />
        <IntelligenceCard title="Risk accounting" value="R based" label="notional, stop risk, realized and unrealized P&L" tone="amber" />
        <IntelligenceCard title="Position engine" value="Realtime" label="open positions update with market movement" tone="emerald" />
      </div>
      <TradesTable />
    </ProductPage>
  );
}
