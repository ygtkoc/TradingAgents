"use client";

import {
  Button,
  Card, CardContent, CardDescription, CardHeader, CardTitle,
  EmptyState, ErrorState, IntelligenceCard, PageHeader, PipelineRail, ProductPage, Skeleton,
} from "@ta/ui";
import { cn, formatCurrency, formatRelative } from "@ta/utils";
import {
  ArrowUpRight, ArrowDownRight, BarChart3, ChevronRight, Clock, Sparkles,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { RecentDecisionsTable } from "@/components/dashboard/recent-decisions-table";
import { RecentTradesTable }    from "@/components/dashboard/recent-trades-table";
import { AccountSummary }       from "@/components/paper/account-summary";
import { PaperOnboardingCard }  from "@/components/paper/paper-onboarding";
import { formatPrice }          from "@/lib/format-price";
import { usePaperAccountMutations } from "@/lib/hooks/mutations/use-paper-account-mutations";
import { usePaperAccount, usePaperAccountEvents } from "@/lib/hooks/queries/use-paper-account";
import { useTrades }            from "@/lib/hooks/queries/use-trades";

export default function PaperTradingPage() {
  const router        = useRouter();
  const acct          = usePaperAccount();
  const hasPaperAccount = !!acct.data;
  const events        = usePaperAccountEvents(100, hasPaperAccount);
  const openTrades    = useTrades({ status: "open",   mode: "paper", limit: 25, enabled: hasPaperAccount });
  const closedTrades  = useTrades({ status: "closed", mode: "paper", limit: 25, enabled: hasPaperAccount });

  useEffect(() => {
    if (acct.isError)
      console.error("paper.page.load.failed", { stage: "paper_account", error: acct.error });
  }, [acct.error, acct.isError]);

  // ── Loading ────────────────────────────────────────────────────────────────
  if (acct.isLoading) {
    return (
      <ProductPage size="xl">
        <Skeleton className="h-9 w-64 rounded-xl" />
        <Skeleton className="h-52 w-full rounded-2xl" />
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-64 rounded-2xl" />
          <Skeleton className="h-64 rounded-2xl" />
        </div>
      </ProductPage>
    );
  }

  // ── No account yet ─────────────────────────────────────────────────────────
  if (!acct.data) {
    return (
      <ProductPage size="md">
        <PageHeader
          eyebrow="Simulation"
          title="Paper trading engine"
          description="Initialize a fully simulated account where autonomous agents analyze real markets and execute paper trades."
        />

        {/* Onboarding card */}
        <div className="relative overflow-hidden rounded-2xl border border-primary/20 bg-gradient-to-br from-primary/8 via-card to-card p-8">
          <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-primary/60 via-cyan-300/35 to-transparent" />
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
      </ProductPage>
    );
  }

  const account       = acct.data;
  const accountStatus = ["active","paused","inactive"].includes(account.status)
    ? account.status as "active"|"paused"|"inactive"
    : "inactive";
  const ledgerEvents = events.data ?? [];
  const totalIncome = ledgerEvents.reduce((sum, event) => {
    const delta = safeNum(event.realized_delta || event.delta);
    return delta > 0 ? sum + delta : sum;
  }, 0);
  const totalExpense = ledgerEvents.reduce((sum, event) => {
    const delta = safeNum(event.realized_delta || event.delta);
    return delta < 0 ? sum + Math.abs(delta) : sum;
  }, 0);
  const totalNet = totalIncome - totalExpense;

  return (
    <ProductPage size="xl">
      <PageHeader
        eyebrow="Paper engine"
        title="Autonomous paper trading"
        description="Simulated execution against live Binance prices with account controls, risk accounting, ledger events, and decision history."
      />

      <div className="grid gap-3 md:grid-cols-4">
        <IntelligenceCard title="Engine state" value={accountStatus} label="paper lifecycle" tone={accountStatus === "active" ? "emerald" : accountStatus === "paused" ? "amber" : "neutral"} />
        <IntelligenceCard title="Income" value={formatCurrency(totalIncome)} label="realized positive ledger movement" tone="emerald" />
        <IntelligenceCard title="Expense" value={formatCurrency(totalExpense)} label="realized negative ledger movement" tone="risk" />
        <IntelligenceCard title="Net ledger" value={`${totalNet >= 0 ? "+" : ""}${formatCurrency(totalNet)}`} label="paper balance delta" tone={totalNet >= 0 ? "cyan" : "risk"} />
      </div>

      <PipelineRail
        steps={[
          { label: "Market feed", state: accountStatus === "active" ? "active" : "idle" },
          { label: "Agent consensus", state: "complete" },
          { label: "Risk check", state: "complete" },
          { label: "Paper fill", state: openTrades.data?.length ? "active" : "idle" },
        ]}
      />

      {/* Account hero */}
      <AccountSummary account={account} />

      <div className="grid gap-3 sm:grid-cols-3">
        <LedgerSummaryButton
          label="Total income"
          value={formatCurrency(totalIncome)}
          tone="income"
          onClick={() => router.push("/paper/income")}
        />
        <LedgerSummaryButton
          label="Total expense"
          value={formatCurrency(totalExpense)}
          tone="expense"
          onClick={() => router.push("/paper/expense")}
        />
        <LedgerSummaryButton
          label="Net ledger"
          value={`${totalNet >= 0 ? "+" : ""}${formatCurrency(totalNet)}`}
          tone={totalNet > 0 ? "income" : totalNet < 0 ? "expense" : "neutral"}
          onClick={() => router.push("/paper/ledger")}
        />
      </div>

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

      {/* Closed trades + issues */}
      <div className="grid gap-4 lg:grid-cols-2">
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

        <Card>
          <CardHeader>
            <CardTitle>Orders & issues</CardTitle>
            <CardDescription>Pending / failed / cancelled paper trades.</CardDescription>
          </CardHeader>
          <CardContent>
            <RecentTradesTable
              limit={25}
              mode="paper"
              statuses={["pending", "failed", "cancelled"]}
              emptyTitle="No pending/failed trades"
              emptyDescription="If an order is pending, fails, or is cancelled, it appears here."
            />
          </CardContent>
        </Card>
      </div>

      {/* Account ledger */}
      <Card>
        <CardHeader>
          <CardTitle>Account ledger</CardTitle>
          <CardDescription>Every paper balance movement, linked to the trade that caused it.</CardDescription>
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
                const cashDelta = safeNum(event.delta);
                const realizedDelta = safeNum(event.realized_delta);
                const eventType = String(event.event_type ?? "");
                const preferRealized = realizedDelta !== 0 || eventType.includes("close") || eventType.includes("settle");
                const visibleDelta = preferRealized ? realizedDelta : cashDelta;
                const balanceAfter = safeNum(event.balance_after);
                const balanceBefore = balanceAfter - cashDelta;
                const trade = event.trades;
                const symbol = trade?.symbol ?? String(event.metadata?.symbol ?? "");
                return (
                  <li
                    key={event.id}
                    className="grid gap-3 rounded-xl border border-border/30 bg-card/40 px-4 py-3 text-[13px] md:grid-cols-[1.2fr_1fr_1fr]"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-foreground">
                          {symbol || event.event_type.replace(/_/g, " ")}
                        </span>
                        {trade?.direction ? (
                          <span className={cn(
                            "rounded-full px-1.5 py-0.5 text-[10px] font-semibold uppercase",
                            trade.direction === "long" ? "bg-success/10 text-success" : "bg-destructive/10 text-destructive",
                          )}>
                            {trade.direction}
                          </span>
                        ) : null}
                        <span className="text-[11px] text-muted-foreground/60">
                          {formatRelative(event.created_at)}
                        </span>
                      </div>
                      <p className="mt-0.5 text-[12px] text-muted-foreground">
                        {event.event_type.replace(/_/g, " ")}
                        {trade?.close_reason ? ` - ${trade.close_reason}` : ""}
                      </p>
                      {event.note ? (
                        <p className="mt-0.5 line-clamp-1 text-[12px] text-muted-foreground">
                          {event.note}
                        </p>
                      ) : null}
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-[12px] tabular-nums md:text-right">
                      <div>
                        <div className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground/50">Entry</div>
                        <div className="font-medium">{trade?.entry_price ? formatPrice(trade.entry_price) : "-"}</div>
                      </div>
                      <div>
                        <div className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground/50">Exit</div>
                        <div className="font-medium">{trade?.exit_price ? formatPrice(trade.exit_price) : "-"}</div>
                      </div>
                    </div>
                    <div className="shrink-0 text-right">
                      <div className={cn(
                        "flex items-center gap-0.5 justify-end font-semibold tabular-nums",
                        visibleDelta > 0 ? "text-success" : visibleDelta < 0 ? "text-destructive" : "text-foreground",
                      )}>
                        {visibleDelta > 0 ? <ArrowUpRight className="h-3.5 w-3.5" /> : visibleDelta < 0 ? <ArrowDownRight className="h-3.5 w-3.5" /> : null}
                        {visibleDelta >= 0 ? "+" : ""}{formatCurrency(visibleDelta)}
                      </div>
                      <div className="mt-0.5 text-[10px] text-muted-foreground/50 tabular-nums">
                        {formatCurrency(balanceBefore)} {"->"} {formatCurrency(balanceAfter)}
                      </div>
                      {trade?.pnl_pct != null ? (
                        <div className={cn(
                          "text-[10px] font-semibold tabular-nums",
                          trade.pnl_pct > 0 ? "text-success" : trade.pnl_pct < 0 ? "text-destructive" : "text-muted-foreground",
                        )}>
                          {trade.pnl_pct >= 0 ? "+" : ""}{Number(trade.pnl_pct).toFixed(2)}%
                        </div>
                      ) : null}
                      {realizedDelta !== cashDelta ? (
                        <div className="text-[10px] text-muted-foreground/50 tabular-nums">
                          cash {cashDelta >= 0 ? "+" : ""}{formatCurrency(cashDelta)}
                        </div>
                      ) : null}
                      </div>
                  </li>
                );
              })}
            </ol>
          )}
        </CardContent>
      </Card>
    </ProductPage>
  );
}

function safeNum(value: unknown): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function LedgerSummaryButton({
  label,
  value,
  tone,
  onClick,
}: {
  label: string;
  value: string;
  tone: "income" | "expense" | "neutral";
  onClick: () => void;
}) {
  return (
    <Button
      type="button"
      variant="outline"
      onClick={onClick}
      className={cn(
        "h-auto justify-between rounded-xl border-border/50 bg-card/55 px-4 py-3 text-left hover:bg-card/80",
        tone === "income" && "hover:border-success/35",
        tone === "expense" && "hover:border-destructive/35",
      )}
    >
      <span className="flex flex-col gap-1">
        <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground/65">
          {label}
        </span>
        <span className={cn(
          "text-xl font-bold tabular-nums",
          tone === "income" ? "text-success" : tone === "expense" ? "text-destructive" : "text-foreground",
        )}>
          {value}
        </span>
      </span>
      <ChevronRight className="h-4 w-4 text-muted-foreground/50" />
    </Button>
  );
}
