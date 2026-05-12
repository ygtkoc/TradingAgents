"use client";

import {
  Badge,
  Card, CardContent, CardDescription, CardHeader, CardTitle,
  EmptyState,
  ErrorState,
  LifecycleBadge,
  ModeBadge,
  PageHeader,
  Skeleton,
  StatusBadge,
} from "@ta/ui";
import { cn, formatCurrency, formatDateTime, formatNumber } from "@ta/utils";
import {
  AlertTriangle, ArrowDown, ArrowUp, BarChart2, Clock,
  ShieldAlert, Zap,
} from "lucide-react";
import { useParams } from "next/navigation";

import { TradeTimeline } from "@/components/trades/trade-timeline";
import { useRiskLogs, useSecurityLogs } from "@/lib/hooks/queries/use-logs";
import { useTrade } from "@/lib/hooks/queries/use-trades";

export default function TradeDetailPage() {
  const params  = useParams<{ tradeId: string }>();
  const tradeId = params.tradeId;
  const { data: trade, isLoading, isError, refetch } = useTrade(tradeId);
  const risk     = useRiskLogs({ tradeId, limit: 20 });
  const security = useSecurityLogs({ limit: 20 });

  if (isError) return <ErrorState onRetry={() => void refetch()} />;

  if (isLoading || !trade) {
    return (
      <div className="mx-auto flex max-w-6xl flex-col gap-5">
        <Skeleton className="h-9 w-64 rounded-xl" />
        <Skeleton className="h-52 w-full rounded-2xl" />
        <div className="grid gap-4 sm:grid-cols-3">
          {[...Array(6)].map((_, i) => <Skeleton key={i} className="h-20 rounded-xl" />)}
        </div>
      </div>
    );
  }

  const pnl          = trade.realized_pnl ?? trade.unrealized_pnl ?? 0;
  const pnlNum       = Number(pnl);
  const isOpen       = trade.status === "open";
  const isProfit     = pnlNum > 0;
  const isLoss       = pnlNum < 0;
  const isLong       = trade.direction === "long" || trade.side === "buy";
  const reconcActive = trade.lifecycle_status === "needs_reconciliation";

  const heroGradient = isProfit
    ? "border-success/20 bg-gradient-to-br from-success/5 via-card to-card"
    : isLoss
      ? "border-destructive/20 bg-gradient-to-br from-destructive/5 via-card to-card"
      : "border-border/50 bg-card/80";

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <PageHeader
        title={`${trade.symbol} · ${trade.direction.toUpperCase()}`}
        description={`Created ${formatDateTime(trade.created_at)}`}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <ModeBadge mode={trade.mode} />
            <StatusBadge status={trade.status} />
            <LifecycleBadge status={trade.lifecycle_status} />
          </div>
        }
      />

      {/* ── Reconciliation alert ─────────────────────────────────────────────── */}
      {reconcActive ? (
        <div className="flex items-start gap-3 rounded-xl border border-destructive/30 bg-destructive/8 p-4 text-[13px] text-destructive backdrop-blur-sm">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <strong className="font-semibold">Reconciliation required.</strong>
            {" "}Trade lifecycle is paused at{" "}
            <code className="rounded bg-destructive/10 px-1 font-mono text-[11px]">needs_reconciliation</code>
            . Operator action required to resolve drift.
            {trade.lifecycle_error ? (
              <div className="mt-1 text-[11px] opacity-70">{trade.lifecycle_error}</div>
            ) : null}
          </div>
        </div>
      ) : null}

      {/* ── P&L hero ─────────────────────────────────────────────────────────── */}
      <div className={cn(
        "relative overflow-hidden rounded-2xl border p-6 backdrop-blur-sm",
        heroGradient,
      )}>
        <div className="flex items-start justify-between gap-6">
          <div className="flex items-center gap-4">
            {/* Direction icon */}
            <div className={cn(
              "flex h-12 w-12 items-center justify-center rounded-2xl border",
              isLong
                ? "border-success/20 bg-success/10"
                : "border-destructive/20 bg-destructive/10",
            )}>
              {isLong
                ? <ArrowUp className="h-6 w-6 text-success" />
                : <ArrowDown className="h-6 w-6 text-destructive" />}
            </div>
            <div>
              <div className="text-[13px] text-muted-foreground/60 uppercase tracking-[0.1em]">
                {isOpen ? "Unrealized P&L" : "Realized P&L"}
              </div>
              <div className={cn(
                "text-3xl font-bold tabular-nums",
                isProfit ? "text-success" : isLoss ? "text-destructive" : "text-foreground",
              )}>
                {isProfit ? "+" : ""}{formatCurrency(pnlNum)}
              </div>
              {trade.r_multiple != null ? (
                <div className={cn(
                  "mt-1 text-[13px] font-semibold",
                  Number(trade.r_multiple) > 0 ? "text-success" : Number(trade.r_multiple) < 0 ? "text-destructive" : "text-muted-foreground",
                )}>
                  {Number(trade.r_multiple) >= 0 ? "+" : ""}{Number(trade.r_multiple).toFixed(2)}R
                  <span className="ml-1 font-normal text-muted-foreground/60">
                    {Number(trade.r_multiple) > 0
                      ? `· won ${Number(trade.r_multiple).toFixed(2)}× risk`
                      : Number(trade.r_multiple) < 0
                        ? `· lost ${Math.abs(Number(trade.r_multiple)).toFixed(2)}× risk`
                        : ""}
                  </span>
                </div>
              ) : null}
            </div>
          </div>

          {/* Quick stats column */}
          <div className="hidden shrink-0 flex-col items-end gap-2 text-right sm:flex">
            {trade.entry_price != null ? (
              <StatPill label="Entry" value={formatCurrency(trade.entry_price)} />
            ) : null}
            {trade.stop_loss != null ? (
              <StatPill label="Stop loss" value={formatCurrency(trade.stop_loss)} color="text-destructive" />
            ) : null}
            {trade.take_profit != null ? (
              <StatPill label="Take profit" value={formatCurrency(trade.take_profit)} color="text-success" />
            ) : null}
          </div>
        </div>

        {/* Exchange / symbol row */}
        <div className="mt-5 flex flex-wrap gap-2 border-t border-border/20 pt-4">
          {[
            { label: "Exchange",      value: trade.exchange },
            { label: "Symbol",        value: trade.symbol, mono: true },
            { label: "Qty",           value: formatNumber(trade.quantity, 8) },
            trade.filled_quantity != null
              ? { label: "Filled",    value: formatNumber(trade.filled_quantity, 8) }
              : null,
            trade.avg_fill_price != null
              ? { label: "Avg fill",  value: formatCurrency(trade.avg_fill_price) }
              : null,
            trade.trailing_stop_price != null
              ? { label: "Trail stop", value: formatCurrency(trade.trailing_stop_price) }
              : null,
            trade.exchange_order_id
              ? { label: "Order ID",  value: trade.exchange_order_id, mono: true }
              : null,
          ].filter(Boolean).map((f) => f && (
            <div key={f.label} className="rounded-xl border border-border/30 bg-card/40 px-3 py-2">
              <div className="text-[9px] font-semibold uppercase tracking-[0.12em] text-muted-foreground/50">{f.label}</div>
              <div className={cn("mt-0.5 text-[12px] font-medium text-foreground", f.mono && "font-mono")}>
                {f.value}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Position sizing card ─────────────────────────────────────────────── */}
      {(trade.risk_amount != null || trade.notional != null || trade.risk_reward_ratio != null) ? (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <BarChart2 className="h-4 w-4 text-muted-foreground/50" />
              <CardTitle>Position sizing</CardTitle>
            </div>
            <CardDescription>Risk parameters computed at entry by the paper execution engine.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {([
                trade.notional       != null ? { label: "Notional",       value: formatCurrency(Number(trade.notional)) } : null,
                trade.risk_amount    != null ? { label: "Risk amount",    value: formatCurrency(Number(trade.risk_amount)) } : null,
                trade.risk_percent   != null ? { label: "Risk %",         value: `${Number(trade.risk_percent).toFixed(2)}%` } : null,
                trade.risk_reward_ratio != null ? { label: "R:R ratio",   value: `1 : ${Number(trade.risk_reward_ratio).toFixed(1)}` } : null,
                trade.expected_reward   != null ? { label: "Expected",    value: formatCurrency(Number(trade.expected_reward)) } : null,
                trade.close_reason ? { label: "Close reason",             value: trade.close_reason.replace(/_/g, " ") } : null,
              ] as const).filter(Boolean).map((f) => f && (
                <div key={f.label} className="rounded-xl border border-border/30 bg-card/40 px-4 py-3">
                  <div className="text-[9px] font-semibold uppercase tracking-[0.12em] text-muted-foreground/50">{f.label}</div>
                  <div className="mt-1 text-[13px] font-medium text-foreground">{f.value}</div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ) : null}

      {/* ── Timeline ─────────────────────────────────────────────────────────── */}
      <TradeTimeline tradeId={trade.id} />

      {/* ── Logs ─────────────────────────────────────────────────────────────── */}
      <div className="grid gap-4 lg:grid-cols-2">
        <LogsCard
          title="Risk logs"
          description="Risk events triggered for this trade."
          isLoading={risk.isLoading}
          items={(risk.data ?? []).map((r) => ({
            id: r.id,
            severity: r.severity,
            type: r.risk_type,
            message: r.message,
            createdAt: r.created_at,
          }))}
          emptyTitle="No risk logs"
        />
        <LogsCard
          title="Security logs"
          description="Recent security events for your account."
          isLoading={security.isLoading}
          items={(security.data ?? []).map((s) => ({
            id: s.id,
            severity: s.severity,
            type: s.event_type,
            message: s.message,
            createdAt: s.created_at,
          }))}
          emptyTitle="No security logs"
        />
      </div>
    </div>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function StatPill({
  label, value, color = "text-foreground",
}: { label: string; value: string; color?: string }) {
  return (
    <div className="rounded-lg border border-border/30 bg-card/40 px-3 py-1.5 text-right">
      <div className="text-[9px] uppercase tracking-[0.12em] text-muted-foreground/50">{label}</div>
      <div className={cn("text-[12px] font-semibold tabular-nums", color)}>{value}</div>
    </div>
  );
}

interface LogItem {
  id: string;
  severity: string;
  type: string;
  message: string;
  createdAt: string;
}

function LogsCard({
  title, description, isLoading, items, emptyTitle,
}: {
  title: string;
  description: string;
  isLoading: boolean;
  items: LogItem[];
  emptyTitle: string;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <ShieldAlert className="h-4 w-4 text-muted-foreground/50" />
          <CardTitle>{title}</CardTitle>
        </div>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-14 rounded-xl" />)}
          </div>
        ) : items.length === 0 ? (
          <EmptyState title={emptyTitle} />
        ) : (
          <ul className="space-y-1.5">
            {items.map((item) => (
              <li
                key={item.id}
                className="rounded-xl border border-border/30 bg-card/40 px-4 py-3"
              >
                <div className="flex items-center justify-between gap-2">
                  <Badge variant={severityVariant(item.severity)} className="text-[10px]">
                    {item.severity}
                  </Badge>
                  <div className="flex items-center gap-1 text-[10px] text-muted-foreground/50">
                    <Clock className="h-3 w-3" />
                    {formatDateTime(item.createdAt)}
                  </div>
                </div>
                <div className="mt-1.5 text-[10px] font-medium uppercase tracking-[0.08em] text-muted-foreground/50">
                  {item.type}
                </div>
                <div className="mt-0.5 text-[12px] text-foreground">{item.message}</div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function severityVariant(s: string): "default" | "secondary" | "warning" | "destructive" | "outline" {
  if (s === "critical" || s === "high") return "destructive";
  if (s === "medium")                    return "warning";
  if (s === "low" || s === "info")       return "secondary";
  return "outline";
}
