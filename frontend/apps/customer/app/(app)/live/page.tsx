"use client";

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  EmptyState,
  IntelligenceCard,
  PageHeader,
  PipelineRail,
  ProductPage,
  Skeleton,
} from "@ta/ui";
import { ShieldAlert, Wallet } from "lucide-react";
import Link from "next/link";

import { useExchangeConnections } from "@/lib/hooks/queries/use-exchange-connections";

export default function LiveTradingPage() {
  const conns = useExchangeConnections();

  return (
    <ProductPage size="xl">
      <PageHeader
        eyebrow="Live execution"
        title="Live trading safety gates"
        description="Real-money execution is disabled by default. Every exchange, platform, risk, and kill-switch gate must pass before an order can leave the system."
      />

      <div className="grid gap-3 md:grid-cols-3">
        <IntelligenceCard title="Default posture" value="Disabled" label="no live order without explicit opt-in" tone="risk" />
        <IntelligenceCard title="Permission model" value="No withdraw" label="trade keys are checked before activation" tone="amber" />
        <IntelligenceCard title="Safety layer" value="Audited" label="risk warning, kill switch, backend gates" tone="emerald" />
      </div>

      <PipelineRail
        steps={[
          { label: "Exchange key", state: "idle" },
          { label: "Permission check", state: "complete" },
          { label: "Risk acknowledgement", state: "risk" },
          { label: "Execution enabled", state: "idle" },
        ]}
      />

      <Card className="border-warning/40 bg-warning/5">
        <CardHeader className="flex flex-row items-start gap-3 space-y-0 pb-3">
          <ShieldAlert className="mt-0.5 h-5 w-5 text-warning" />
          <div>
            <CardTitle className="text-base">Live trading is disabled</CardTitle>
            <CardDescription>
              All of these must be true for live orders to be submitted:
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <ul className="grid gap-2 text-sm md:grid-cols-2">
            {[
              "An exchange connection exists and passed a permission check",
              "The connection has can_trade=true, can_withdraw=false",
              "You explicitly enable live trading on the connection",
              "platform_settings.live_execution_enabled = true",
              "Backend ENABLE_LIVE_EXECUTION = true",
              "Risk-warning acknowledged",
              "Global kill switch enabled",
            ].map((gate) => (
              <li key={gate} className="flex items-start gap-2 rounded-md border border-warning/15 bg-warning/5 px-3 py-2">
                <span className="mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-warning" />
                <span className="text-muted-foreground">{gate}</span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <div className="space-y-1">
            <CardTitle>Exchange connections</CardTitle>
            <CardDescription>Connections required for live trading.</CardDescription>
          </div>
          <Link href="/settings/exchanges">
            <Button size="sm" variant="outline">Manage</Button>
          </Link>
        </CardHeader>
        <CardContent>
          {conns.isLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : (conns.data ?? []).length === 0 ? (
            <EmptyState
              icon={Wallet}
              title="No exchange connected"
              description="Connect an exchange in Settings -> Exchanges. Until then, all trading happens in paper mode."
              action={
                <Link href="/settings/exchanges">
                  <Button>Connect exchange</Button>
                </Link>
              }
            />
          ) : (
            <ul className="divide-y divide-border/35 overflow-hidden rounded-lg border border-border/55 bg-card/35">
              {conns.data!.map((connection) => (
                <li key={connection.id} className="flex flex-col gap-3 p-4 text-sm sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <div className="font-medium">{connection.label ?? connection.exchange}</div>
                    <div className="text-xs text-muted-foreground">{connection.exchange}</div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {connection.can_trade
                      ? <Badge variant="success">trade</Badge>
                      : <Badge variant="secondary">read-only</Badge>}
                    {connection.can_withdraw
                      ? <Badge variant="destructive">withdraw</Badge>
                      : <Badge variant="outline">no withdraw</Badge>}
                    {connection.is_active
                      ? <Badge variant="default">active</Badge>
                      : <Badge variant="secondary">inactive</Badge>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Live trades</CardTitle>
          <CardDescription>Real-money trades only.</CardDescription>
        </CardHeader>
        <CardContent>
          <EmptyState
            title="No live trades"
            description="Live trades appear here once a connection is enabled, gates are satisfied, and an agent decision opens a position."
          />
        </CardContent>
      </Card>
    </ProductPage>
  );
}
