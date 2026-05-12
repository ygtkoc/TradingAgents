"use client";

import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, EmptyState, PageHeader, Skeleton } from "@ta/ui";
import { ShieldAlert, Wallet } from "lucide-react";
import Link from "next/link";

import { useExchangeConnections } from "@/lib/hooks/queries/use-exchange-connections";

export default function LiveTradingPage() {
  const conns = useExchangeConnections();

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageHeader
        title="Live trading"
        description="Real-money execution. Disabled by default — every gate must be satisfied before any live order is placed."
      />

      {/* Disabled-by-default banner */}
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
          <ul className="space-y-1.5 text-sm">
            {[
              "An exchange connection exists and passed a permission check",
              "The connection has can_trade=true, can_withdraw=false",
              "You explicitly enable live trading on the connection",
              "platform_settings.live_execution_enabled = true",
              "Backend ENABLE_LIVE_EXECUTION = true",
              "Risk-warning acknowledged",
              "Global kill switch enabled",
            ].map((g) => (
              <li key={g} className="flex items-start gap-2">
                <span className="mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-warning" />
                <span className="text-muted-foreground">{g}</span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      {/* Exchange connections summary */}
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
              description="Connect an exchange in Settings → Exchanges. Until then, all trading happens in paper mode."
              action={
                <Link href="/settings/exchanges">
                  <Button>Connect exchange</Button>
                </Link>
              }
            />
          ) : (
            <ul className="divide-y rounded-md border">
              {conns.data!.map((c) => (
                <li key={c.id} className="flex items-center justify-between p-3 text-sm">
                  <div>
                    <div className="font-medium">{c.label ?? c.exchange}</div>
                    <div className="text-xs text-muted-foreground">{c.exchange}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    {c.can_trade
                      ? <Badge variant="success">trade</Badge>
                      : <Badge variant="secondary">read-only</Badge>}
                    {c.can_withdraw
                      ? <Badge variant="destructive">withdraw</Badge>
                      : <Badge variant="outline">no withdraw</Badge>}
                    {c.is_active
                      ? <Badge variant="default">active</Badge>
                      : <Badge variant="secondary">inactive</Badge>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* Live trades list — empty for now (real data only) */}
      <Card>
        <CardHeader>
          <CardTitle>Live trades</CardTitle>
          <CardDescription>Real-money trades only.</CardDescription>
        </CardHeader>
        <CardContent>
          <EmptyState
            title="No live trades"
            description="Live trades will appear here once a connection is enabled, gates are satisfied, and an agent decision opens a position."
          />
        </CardContent>
      </Card>
    </div>
  );
}
