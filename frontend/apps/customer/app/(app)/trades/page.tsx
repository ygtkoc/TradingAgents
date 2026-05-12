"use client";

import { PageHeader } from "@ta/ui";

import { TradesTable } from "@/components/trades/trades-table";

export default function TradesPage() {
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageHeader
        title="Trades"
        description="All trades across your bots. Filter by status and mode."
      />
      <TradesTable />
    </div>
  );
}
