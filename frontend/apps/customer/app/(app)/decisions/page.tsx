"use client";

import { PageHeader } from "@ta/ui";

import { DecisionsTable } from "@/components/decisions/decisions-table";

export default function DecisionsPage() {
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageHeader
        title="Decisions"
        description="Agent-run decisions and pending approvals. Approve or reject from this view."
      />
      <DecisionsTable />
    </div>
  );
}
