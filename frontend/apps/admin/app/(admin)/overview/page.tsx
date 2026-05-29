import { Card, CardContent, CardDescription, CardHeader, CardTitle, IntelligenceCard, PageHeader, PipelineRail, ProductPage } from "@ta/ui";

export default function AdminOverviewPage() {
  return (
    <ProductPage size="xl">
      <PageHeader
        eyebrow="Operations"
        title="Platform overview"
        description="Worker health, queue pressure, reconciliation state, and safety posture for the multi-agent trading platform."
      />

      <div className="grid gap-3 md:grid-cols-4">
        <IntelligenceCard title="Workers online" value="-" label="agent, execution, position" tone="cyan" />
        <IntelligenceCard title="Open trades" value="-" label="active lifecycle records" tone="blue" />
        <IntelligenceCard title="Pending decisions" value="-" label="approval and execution backlog" tone="amber" />
        <IntelligenceCard title="Reconciliation" value="-" label="positions needing operator review" tone="risk" />
      </div>

      <PipelineRail
        steps={[
          { label: "Signal queue", state: "complete" },
          { label: "Agent workers", state: "active" },
          { label: "Execution guard", state: "complete" },
          { label: "Position lifecycle", state: "idle" },
        ]}
      />

      <Card>
        <CardHeader>
          <CardTitle>Operations note</CardTitle>
          <CardDescription>
            Admin writes go through audited Edge Functions. The frontend cannot directly mutate protected trade, decision, signal, or platform setting tables.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm leading-6 text-muted-foreground">
          Kill switch and live-execution flags are subscribed in real time across admin sessions. Service-role access remains blocked from browser code.
        </CardContent>
      </Card>
    </ProductPage>
  );
}
