import { Card, CardContent, CardDescription, CardHeader, CardTitle, IntelligenceCard, PageHeader, PipelineRail, ProductPage } from "@ta/ui";

export default function AdminOverviewPage() {
  return (
    <ProductPage size="xl">
      <PageHeader
        eyebrow="Operations"
        title="Admin cockpit"
        description="A compact operating view for customer activity, execution safety, worker flow, and knowledge-gated trading decisions."
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

      <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
      <Card className="border-border/70 bg-card/70">
        <CardHeader>
          <CardTitle>Today&apos;s operator focus</CardTitle>
          <CardDescription>
            Keep this plane quiet, legible, and built for repeated checks.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm leading-6 text-muted-foreground">
          Start with pending decisions, reconciliation, and high-severity logs. Trading Brain changes should be treated as platform-wide policy changes because global rules affect every customer bot.
        </CardContent>
      </Card>
      <Card className="border-slate-700 bg-slate-900/60">
        <CardHeader>
          <CardTitle>Global Trading Brain</CardTitle>
          <CardDescription>Central knowledge now lives in the admin plane.</CardDescription>
        </CardHeader>
        <CardContent>
          <a className="inline-flex rounded-md bg-blue-500 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-400" href="/trading-brain">
            Open knowledge manager
          </a>
        </CardContent>
      </Card>
      </div>
    </ProductPage>
  );
}
