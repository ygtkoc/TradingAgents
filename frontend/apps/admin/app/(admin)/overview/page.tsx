import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@ta/ui";

export default function AdminOverviewPage() {
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Platform overview</h1>
        <p className="text-sm text-muted-foreground">
          Placeholder. Worker health, queue depth, latency, and platform KPIs land in a later task.
        </p>
      </header>

      <div className="grid gap-4 md:grid-cols-4">
        {[
          { title: "Workers online",    value: "—" },
          { title: "Open trades",       value: "—" },
          { title: "Pending decisions", value: "—" },
          { title: "needs_reconciliation", value: "—" },
        ].map((kpi) => (
          <Card key={kpi.title}>
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {kpi.title}
              </CardTitle>
            </CardHeader>
            <CardContent className="text-3xl font-semibold tabular-nums">
              {kpi.value}
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Operations note</CardTitle>
          <CardDescription>
            Every admin write goes through an Edge Function. The kill switch
            and live-execution flag are subscribed in real time across all
            admin sessions.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          The frontend cannot insert/update trades, decisions, signals, or platform_settings
          directly — RLS blocks it and ESLint blocks the service-role import.
        </CardContent>
      </Card>
    </div>
  );
}
