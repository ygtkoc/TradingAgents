"use client";

import { Button, IntelligenceCard, PageHeader, PipelineRail, ProductPage } from "@ta/ui";
import { Plus } from "lucide-react";
import Link from "next/link";

import { BotsTable } from "@/components/bots/bots-table";

export default function BotsPage() {
  return (
    <ProductPage size="xl">
      <PageHeader
        eyebrow="Agent fleet"
        title="Autonomous agents"
        description="Configure, supervise, and deploy trading agents across paper and live-gated execution modes."
        actions={
          <Link href="/bots/new">
            <Button size="sm" className="gap-1.5">
              <Plus className="h-4 w-4" />
              New bot
            </Button>
          </Link>
        }
      />
      <div className="grid gap-3 md:grid-cols-3">
        <IntelligenceCard title="Orchestration" value="5+ agents" label="analysis, critique, risk, security, sentiment" tone="cyan" />
        <IntelligenceCard title="Decision policy" value="Consensus" label="signals require gated multi-agent agreement" tone="purple" />
        <IntelligenceCard title="Execution state" value="Risk first" label="wallet risk and safety controls are enforced server-side" tone="emerald" />
      </div>
      <PipelineRail
        steps={[
          { label: "Market ingest", state: "complete" },
          { label: "Agent analysis", state: "active" },
          { label: "Risk audit", state: "complete" },
          { label: "Execution gate", state: "idle" },
        ]}
      />
      <BotsTable />
    </ProductPage>
  );
}
