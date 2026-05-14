"use client";

import {
  Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle,
  EmptyState, KpiCard, PageHeader, Skeleton,
} from "@ta/ui";
import { DailyPnLChart, EquityCurve, type DailyPnLPoint, type EquityPoint } from "@ta/ui/charts";
import { cn, formatCurrency, formatRelative } from "@ta/utils";
import {
  Activity, ArrowRight, Bot, BarChart3, Sparkles, TrendingDown, TrendingUp,
  Wallet, Zap,
} from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";

import { RecentDecisionsTable } from "@/components/dashboard/recent-decisions-table";
import { RecentTradesTable }    from "@/components/dashboard/recent-trades-table";
import { PendingApprovalsPanel } from "@/components/dashboard/pending-approvals-panel";
import { useBots }              from "@/lib/hooks/queries/use-bots";
import { useDecisions }         from "@/lib/hooks/queries/use-decisions";
import { useExchangeConnections } from "@/lib/hooks/queries/use-exchange-connections";
import { usePaperAccount }      from "@/lib/hooks/queries/use-paper-account";
import { isFilledPosition, useTrades } from "@/lib/hooks/queries/use-trades";

export default function DashboardPage() {
  const acct           = usePaperAccount();
  const hasPaperAccount = !!acct.data;
  const bots           = useBots();
  const trades         = useTrades({ limit: 200, enabled: hasPaperAccount });
  const pending        = useDecisions({ approval: "pending", limit: 50, enabled: hasPaperAccount });
  const conns          = useExchangeConnections();

  // ── Derive chart series from real trades ──────────────────────────────────
  const { equity, daily, openCount, realized, unrealized, winRate } = useMemo(() => {
    const all    = trades.data ?? [];
    const open   = all.filter(isFilledPosition);
    const closed = all
      .filter((t) => t.status === "closed" && t.closed_at)
      .sort((a, b) => (a.closed_at ?? "").localeCompare(b.closed_at ?? ""));

    let cum = 0;
    const equity: EquityPoint[] = closed.map((t) => {
      cum += t.realized_pnl ?? 0;
      return { date: (t.closed_at ?? "").slice(0, 10), equity: cum };
    });

    const byDay = new Map<string, number>();
    for (const t of closed) {
      const d = (t.closed_at ?? "").slice(0, 10);
      byDay.set(d, (byDay.get(d) ?? 0) + (t.realized_pnl ?? 0));
    }
    const daily: DailyPnLPoint[] = Array.from(byDay, ([date, pnl]) => ({ date, pnl }));

    const wins    = closed.filter((t) => (t.realized_pnl ?? 0) > 0).length;
    const winRate = closed.length > 0 ? (wins / closed.length) * 100 : null;

    return {
      equity,
      daily,
      openCount:  open.length,
      realized:   closed.reduce((s, t) => s + (t.realized_pnl ?? 0), 0),
      unrealized: open.reduce((s, t) => s + (t.unrealized_pnl ?? 0), 0),
      winRate,
    };
  }, [trades.data]);

  const isLoading = acct.isLoading || trades.isLoading || bots.isLoading;

  // ── Onboarding ─────────────────────────────────────────────────────────────
  if (!acct.isLoading && !acct.data) {
    return (
      <div className="mx-auto flex max-w-3xl flex-col gap-6">
        <PageHeader
          title="Welcome to TradingAgents"
          description="Run a multi-agent AI trading simulation against live Binance market data."
        />

        {/* Hero CTA */}
        <div className="relative overflow-hidden rounded-2xl border border-primary/20 bg-gradient-to-br from-primary/8 via-card to-card p-8">
          {/* Glow backdrop */}
          <div className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-primary/10 blur-3xl" />
          <div className="pointer-events-none absolute -bottom-10 -left-10 h-48 w-48 rounded-full bg-primary/5 blur-2xl" />

          <div className="relative flex flex-col gap-6 md:flex-row md:items-center">
            <div className="flex-1 space-y-3">
              <div className="flex items-center gap-2">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/20 ring-1 ring-primary/30">
                  <Sparkles className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <div className="font-semibold text-foreground">Paper trading simulation</div>
                  <div className="text-[12px] text-muted-foreground">No real money · No API keys required</div>
                </div>
              </div>

              <p className="text-[13px] leading-relaxed text-muted-foreground">
                Choose a starting balance. The autonomous engine seeds signals every few minutes,
                runs 5+ AI agents in parallel, and opens paper trades when the pipeline reaches
                consensus. All against live Binance prices.
              </p>

              <div className="flex flex-wrap gap-4 text-[12px] text-muted-foreground">
                {[
                  { icon: Bot,       label: "Multi-agent pipeline" },
                  { icon: BarChart3, label: "Live market data" },
                  { icon: Zap,       label: "Autonomous decisions" },
                ].map(({ icon: Icon, label }) => (
                  <div key={label} className="flex items-center gap-1.5">
                    <Icon className="h-3.5 w-3.5 text-primary/70" />
                    <span>{label}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex shrink-0 flex-col items-start gap-2 md:items-end">
              <Link href="/paper">
                <Button size="lg" className="gap-2">
                  Create paper account
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
              <span className="text-[11px] text-muted-foreground/60">Takes ~30 seconds</span>
            </div>
          </div>
        </div>

        {/* Feature grid */}
        <div className="grid gap-3 sm:grid-cols-3">
          {[
            {
              icon: Bot,
              title: "5+ AI Agents",
              desc: "Technical, price action, risk, security & sentiment agents vote on every signal.",
            },
            {
              icon: BarChart3,
              title: "15+ Indicators",
              desc: "RSI, MACD, VWAP, Bollinger, CCI, Stochastic, S/R, market structure & more.",
            },
            {
              icon: Activity,
              title: "Realtime tracking",
              desc: "P&L, equity curve and agent decisions update automatically as the engine runs.",
            },
          ].map(({ icon: Icon, title, desc }) => (
            <Card key={title} className="p-4">
              <div className="mb-2 flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
                <Icon className="h-4 w-4 text-primary" />
              </div>
              <div className="text-[13px] font-semibold text-foreground">{title}</div>
              <div className="mt-1 text-[12px] text-muted-foreground">{desc}</div>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  // ── Account exists ──────────────────────────────────────────────────────────
  const a           = acct.data;
  const start       = a ? Number(a.starting_balance) : 0;
  const rawAccountRealized = a ? Number(a.realized_pnl ?? 0) : 0;
  const rawAccountUnrealized = a ? Number(a.unrealized_pnl ?? 0) : 0;
  const accountRealized = rawAccountRealized !== 0 ? rawAccountRealized : realized;
  const accountUnrealized = rawAccountUnrealized !== 0 ? rawAccountUnrealized : unrealized;
  const accountBalance = a ? Number(a.balance ?? 0) : 0;
  const accountEquity = a ? Number(a.equity ?? 0) : 0;
  const equityValue = accountBalance > 0
    ? accountBalance + accountUnrealized
    : accountEquity;
  const change      = start > 0 ? ((equityValue - start) / start) * 100 : 0;
  const isPositive  = change >= 0;
  const acctStatus  = a?.status ?? "inactive";

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <PageHeader
        title="Dashboard"
        description="Live overview of your paper account, bots, and agent decisions."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Badge
              variant={
                acctStatus === "active"   ? "success"
                : acctStatus === "paused" ? "warning"
                : "secondary"
              }
              className="gap-1"
            >
              {acctStatus === "active" && (
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-60" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-success" />
                </span>
              )}
              paper · {acctStatus}
            </Badge>
            <Link href="/paper">
              <Button size="sm" variant="outline" className="gap-1.5">
                Manage
                <ArrowRight className="h-3 w-3" />
              </Button>
            </Link>
          </div>
        }
      />

      {/* ── KPI strip ───────────────────────────────────────────────────────── */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
        <KpiCard
          label="Equity"
          value={formatCurrency(equityValue)}
          loading={isLoading}
          accent={isPositive ? "green" : "red"}
          trend={isPositive ? "up" : "down"}
          hint={
            <span className={cn("flex items-center gap-1 tabular-nums font-medium",
              isPositive ? "text-success" : "text-destructive",
            )}>
              {isPositive
                ? <TrendingUp className="h-3 w-3" />
                : <TrendingDown className="h-3 w-3" />}
              {isPositive ? "+" : ""}{change.toFixed(2)}% vs start
            </span>
          }
        />
        <KpiCard
          label="Balance"
          value={formatCurrency(a ? Number(a.balance) : 0)}
          loading={isLoading}
        />
        <KpiCard
          label="Realized P&L"
          value={formatCurrency(accountRealized)}
          loading={isLoading}
          trend={accountRealized > 0 ? "up" : accountRealized < 0 ? "down" : "flat"}
          accent={accountRealized > 0 ? "green" : accountRealized < 0 ? "red" : "none"}
        />
        <KpiCard
          label="Unrealized P&L"
          value={formatCurrency(accountUnrealized)}
          loading={isLoading}
          trend={accountUnrealized > 0 ? "up" : accountUnrealized < 0 ? "down" : "flat"}
          accent={accountUnrealized > 0 ? "green" : accountUnrealized < 0 ? "red" : "none"}
        />
        <KpiCard
          label="Open trades"
          value={openCount}
          loading={isLoading}
          accent={openCount > 0 ? "blue" : "none"}
          hint={openCount > 0 ? "positions live" : "no open positions"}
        />
        <KpiCard
          label="Win rate"
          value={winRate != null ? `${winRate.toFixed(0)}%` : "—"}
          loading={isLoading || trades.isLoading}
          accent={winRate != null && winRate >= 50 ? "green" : winRate != null ? "red" : "none"}
          trend={winRate != null && winRate >= 50 ? "up" : winRate != null ? "down" : undefined}
          hint={
            (pending.data?.length ?? 0) > 0
              ? <span className="text-warning">{pending.data!.length} pending decision{pending.data!.length !== 1 ? "s" : ""}</span>
              : "decisions all clear"
          }
        />
      </div>

      {/* ── Pending approvals ───────────────────────────────────────────────── */}
      <PendingApprovalsPanel />

      {/* ── Charts ──────────────────────────────────────────────────────────── */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Equity curve</CardTitle>
                <CardDescription>Cumulative realized P&L over closed trades.</CardDescription>
              </div>
              <TrendingUp className="h-4 w-4 text-muted-foreground/40" />
            </div>
          </CardHeader>
          <CardContent>
            {isLoading
              ? <Skeleton className="h-64 w-full rounded-lg" />
              : equity.length === 0
                ? <EmptyState
                    title="No closed trades yet"
                    description={
                      acctStatus === "active"
                        ? "The equity curve fills in as paper trades close."
                        : "Start the autonomous engine on the Paper page."
                    }
                  />
                : <EquityCurve data={equity} />}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Daily P&L</CardTitle>
                <CardDescription>Realized gains / losses per day.</CardDescription>
              </div>
              <BarChart3 className="h-4 w-4 text-muted-foreground/40" />
            </div>
          </CardHeader>
          <CardContent>
            {isLoading
              ? <Skeleton className="h-52 w-full rounded-lg" />
              : daily.length === 0
                ? <EmptyState title="No daily P&L yet" />
                : <DailyPnLChart data={daily} />}
          </CardContent>
        </Card>
      </div>

      {/* ── Recent activity ──────────────────────────────────────────────────── */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Recent trades</CardTitle>
                <CardDescription>Latest closed & open positions.</CardDescription>
              </div>
              <Link href="/trades">
                <Button size="sm" variant="ghost" className="gap-1 text-[12px] text-muted-foreground">
                  View all <ArrowRight className="h-3 w-3" />
                </Button>
              </Link>
            </div>
          </CardHeader>
          <CardContent>
            {isLoading
              ? <Skeleton className="h-40 w-full rounded-lg" />
              : (trades.data ?? []).length === 0
                ? <EmptyState
                    title="No trades yet"
                    description={
                      acctStatus === "active"
                        ? "Signals are seeded continuously. Once an agent decision resolves to open_long or open_short, the trade appears here."
                        : "Start autonomous trading on the Paper page."
                    }
                  />
                : <RecentTradesTable />}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Agent decisions</CardTitle>
                <CardDescription>Multi-agent pipeline outcomes.</CardDescription>
              </div>
              <Link href="/decisions">
                <Button size="sm" variant="ghost" className="gap-1 text-[12px] text-muted-foreground">
                  View all <ArrowRight className="h-3 w-3" />
                </Button>
              </Link>
            </div>
          </CardHeader>
          <CardContent>
            <RecentDecisionsTable />
          </CardContent>
        </Card>
      </div>

      {/* ── Live trading nudge ───────────────────────────────────────────────── */}
      {(conns.data ?? []).length === 0 ? (
        <Card className="border-border/30 bg-gradient-to-r from-card via-card to-card/50">
          <CardHeader className="flex flex-row items-start gap-3 space-y-0 pb-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted">
              <Wallet className="h-4 w-4 text-muted-foreground" />
            </div>
            <div className="flex-1 space-y-1">
              <CardTitle className="text-[14px]">Connect an exchange for live trading</CardTitle>
              <CardDescription>
                Live trading is off by default. Connect a read+trade API key (no withdraw) to enable it.
              </CardDescription>
            </div>
            <Link href="/settings/exchanges">
              <Button size="sm" variant="outline" className="shrink-0">
                Manage exchanges
              </Button>
            </Link>
          </CardHeader>
        </Card>
      ) : null}
    </div>
  );
}
