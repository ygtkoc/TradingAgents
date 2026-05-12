"use client";

import {
  Card, CardContent, CardDescription, CardHeader, CardTitle,
  EmptyState, ErrorState, PageHeader, Skeleton,
} from "@ta/ui";
import { cn, formatCurrency, formatRelative } from "@ta/utils";
import {
  ArrowUpRight, ArrowDownRight, BarChart3, Clock, Sparkles,
} from "lucide-react";
import { useEffect } from "react";

import { RecentDecisionsTable } from "@/components/dashboard/recent-decisions-table";
import { RecentTradesTable }    from "@/components/dashboard/recent-trades-table";
import { AccountSummary }       from "@/components/paper/account-summary";
import { PaperOnboardingCard }  from "@/components/paper/paper-onboarding";
import { usePaperAccountMutations } from "@/lib/hooks/mutations/use-paper-account-mutations";
import { usePaperAccount, usePaperAccountEvents } from "@/lib/hooks/queries/use-paper-account";
import { useTrades }            from "@/lib/hooks/queries/use-trades";

export default function PaperTradingPage() {
  const acct          = usePaperAccount();
  const hasPaperAccount = !!acct.data;
  const events        = usePaperAccountEvents(20, hasPaperAccount);
  const openTrades    = useTrades({ status: "open",   mode: "paper", limit: 25, enabled: hasPaperAccount });
  const closedTrades  = useTrades({ status: "closed", mode: "paper", limit: 25, enabled: hasPaperAccount });

  useEffect(() => {
    if (acct.isError)
      console.error("paper.page.load.failed", { stage: "paper_account", error: acct.error });
  }, [acct.error, acct.isError]);

  // ── Loading ────────────────────────────────────────────────────────────────
  if (acct.isLoading) {
    return (
      <div className="mx-auto flex max-w-6xl flex-col gap-5">
        <Skeleton className="h-9 w-64 rounded-xl" />
        <Skeleton className="h-52 w-full rounded-2xl" />
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-64 rounded-2xl" />
          <Skeleton className="h-64 rounded-2xl" />
        </div>
      </div>
    );
  }

  // ── No account yet ─────────────────────────────────────────────────────────
  if (!acct.data) {
    return (
      <div className="mx-auto flex max-w-3xl flex-col gap-5">
        <PageHeader
          title="Paper trading"
          description="Run autonomous AI agents against live Binance prices with a fully simulated balance."
        />

        {/* Onboarding card */}
        <div className="relative overflow-hidden rounded-2xl border border-primary/20 bg-gradient-to-br from-primary/8 via-card to-card p-8">
          <div className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full bg-primary/10 blur-3xl" />
          <div className="relative flex items-start gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-primary/15 ring-1 ring-primary/20">
              <Sparkles className="h-6 w-6 text-primary" />
            </div>
            <div className="flex-1">
              <div className="text-[16px] font-bold text-foreground">Start a paper-trading simulation</div>
              <div className="mt-1 text-[13px] text-muted-foreground">
                Pick a starting balance. The autonomous engine seeds signals, runs multi-agent decisions,
                and simulates trades on real market data.
              </div>
              <div className="mt-6">
                <PaperOnboardingCard />
              </div>
            </div>
          </div>
        </div>

        {acct.isError ? (
          <ErrorState
            title="Paper account temporarily unavailable"
            message="Try reloading or creating again."
            onRetry={() => void acct.refetch()}
          />
        ) : null}
      </div>
    );
  }

  const account       = acct.data;
  const accountStatus = ["active","paused","inactive"].includes(account.status)
    ? account.status as "active"|"paused"|"inactive"
    : "inactive";

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5">
      <PageHeader
        title="Paper trading"
        description="Autonomous simulation against live Binance prices. Adjust or reset anytime."
      />

      {/* Account hero */}
      <AccountSummary account={account} />

      {/* Inactive hint */}
      {accountStatus === "inactive" ? (
        <div className="flex items-start gap-3 rounded-2xl border border-border/40 bg-card/60 p-4 text-[13px]">
          <Clock className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground/50" />
          <div>
            <span className="font-medium text-foreground">Account ready — press Start above</span>
            <p className="mt-0.5 text-muted-foreground">
              Funded with {formatCurrency(Number(account.starting_balance))}. Once started, the engine
              seeds signals every few minutes and opens trades when agents reach consensus.
            </p>
          </div>
        </div>
      ) : null}

      {/* Open trades + Agent decisions */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Open positions</CardTitle>
                <CardDescription>P&L updates automatically as prices move.</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {openTrades.isError ? (
              <ErrorState
                title="Positions temporarily unavailable"
                onRetry={() => void openTrades.refetch()}
              />
            ) : openTrades.isLoading ? (
              <Skeleton className="h-40 w-full rounded-xl" />
            ) : (openTrades.data ?? []).length === 0 ? (
              <EmptyState
                title="No open positions"
                description={
                  accountStatus === "active"
                    ? "The next agent decision resolving to open_long / open_short will create a trade."
                    : "Start the autonomous engine above."
                }
              />
            ) : (
              <RecentTradesTable limit={25} status="open" mode="paper" />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Agent decisions</CardTitle>
                <CardDescription>Latest multi-agent pipeline outcomes.</CardDescription>
              </div>
              <BarChart3 className="h-4 w-4 text-muted-foreground/30" />
            </div>
          </CardHeader>
          <CardContent>
            <RecentDecisionsTable limit={10} />
          </CardContent>
        </Card>
      </div>

      {/* Closed trades */}
      <Card>
        <CardHeader>
          <CardTitle>Closed positions</CardTitle>
          <CardDescription>Realized outcomes contribute to the realized P&L above.</CardDescription>
        </CardHeader>
        <CardContent>
          {closedTrades.isError ? (
            <ErrorState title="Closed trades unavailable" onRetry={() => void closedTrades.refetch()} />
          ) : closedTrades.isLoading ? (
            <Skeleton className="h-40 w-full rounded-xl" />
          ) : (closedTrades.data ?? []).length === 0 ? (
            <EmptyState title="No closed positions yet" />
          ) : (
            <RecentTradesTable limit={25} status="closed" mode="paper" />
          )}
        </CardContent>
      </Card>

      {/* Account events */}
      <Card>
        <CardHeader>
          <CardTitle>Account events</CardTitle>
          <CardDescription>Audit trail of every balance change.</CardDescription>
        </CardHeader>
        <CardContent>
          {events.isError ? (
            <ErrorState title="Events unavailable" onRetry={() => void events.refetch()} />
          ) : events.isLoading ? (
            <Skeleton className="h-32 w-full rounded-xl" />
          ) : (events.data ?? []).length === 0 ? (
            <EmptyState title="No events yet" />
          ) : (
            <ol className="space-y-1.5">
              {events.data!.map((event) => {
                const delta = safeNum(event.delta);
                return (
                  <li
                    key={event.id}
                    className="flex items-start justify-between gap-4 rounded-xl border border-border/30 bg-card/40 px-4 py-3 text-[13px]"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-foreground">
                          {event.event_type.replace(/_/g, " ")}
                        </span>
                        <span className="text-[11px] text-muted-foreground/60">
                          {formatRelative(event.created_at)}
                        </span>
                      </div>
                      {event.note ? (
                        <p className="mt-0.5 line-clamp-1 text-[12px] text-muted-foreground">
                          {event.note}
                        </p>
                      ) : null}
                    </div>
                    <div className="shrink-0 text-right">
                      <div className={cn(
                        "flex items-center gap-0.5 justify-end font-semibold tabular-nums",
                        delta > 0 ? "text-success" : delta < 0 ? "text-destructive" : "text-foreground",
                      )}>
                        {delta > 0 ? <ArrowUpRight className="h-3.5 w-3.5" /> : delta < 0 ? <ArrowDownRight className="h-3.5 w-3.5" /> : null}
                        {delta >= 0 ? "+" : ""}{formatCurrency(delta)}
                      </div>
                      <div className="text-[10px] text-muted-foreground/50 tabular-nums">
                        bal {formatCurrency(safeNum(event.balance_after))}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function safeNum(value: unknown): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}
