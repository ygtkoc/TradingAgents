"use client";

import { IntelligenceCard, PageHeader, ProductPage } from "@ta/ui";

import { DecisionsTable } from "@/components/decisions/decisions-table";

export default function DecisionsPage() {
  return (
    <ProductPage size="xl">
      <PageHeader
        eyebrow="Decision ledger"
        title="Agent decisions"
        description="Audited outcomes from the multi-agent pipeline, including approvals, confidence, risk posture, and execution intent."
      />
      <div className="grid gap-3 md:grid-cols-4">
        <IntelligenceCard title="Signal quality" value="Scored" label="weighted agent evidence" tone="blue" />
        <IntelligenceCard title="Confidence" value="Visible" label="every decision exposes conviction" tone="cyan" />
        <IntelligenceCard title="Safety layer" value="Required" label="risk and security agents can veto" tone="risk" />
        <IntelligenceCard title="Audit trail" value="Immutable" label="decision history remains inspectable" tone="purple" />
      </div>
      <DecisionsTable />
    </ProductPage>
  );
}
