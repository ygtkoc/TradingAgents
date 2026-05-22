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
  AlertTriangle, ArrowDown, ArrowUp, BarChart2, Brain, Clock,
  ShieldAlert, Target, Zap,
} from "lucide-react";
import type { Trade } from "@ta/types";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";

import { TradeTimeline } from "@/components/trades/trade-timeline";
import { formatPrice } from "@/lib/format-price";
import { useAgentOutputs, useDecisionAgentRuns } from "@/lib/hooks/queries/use-decision-detail";
import { useRiskLogs, useSecurityLogs } from "@/lib/hooks/queries/use-logs";
import { isFilledPosition, useTrade } from "@/lib/hooks/queries/use-trades";
import { supabase } from "@/lib/supabase/client";

export default function TradeDetailPage() {
  const params  = useParams<{ tradeId: string }>();
  const tradeId = params.tradeId;
  const { data: trade, isLoading, isError, refetch } = useTrade(tradeId);
  const risk     = useRiskLogs({ tradeId, limit: 20 });
  const security = useSecurityLogs({ limit: 20 });
  const runs     = useDecisionAgentRuns(trade?.trade_decision_id ?? null);
  const run      = runs.data?.[0] ?? null;
  const outputs  = useAgentOutputs(run?.id ?? null);

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

  const isOpen       = isFilledPosition(trade);
  const isOpenLike   = isOpen || trade.status === "simulated";
  const pnl          = isOpenLike
    ? trade.unrealized_pnl ?? trade.pnl ?? 0
    : trade.realized_pnl ?? trade.pnl ?? 0;
  const pnlNum       = Number(pnl);
  const pnlPct       = trade.pnl_pct != null ? Number(trade.pnl_pct) : null;
  const isProfit     = pnlNum > 0;
  const isLoss       = pnlNum < 0;
  const isLong       = trade.direction === "long" || trade.side === "buy";
  const reconcActive = trade.lifecycle_status === "needs_reconciliation";
  const latestPrice  = toNum(trade.metadata?.latest_price);

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
      <TradeStatePanel trade={trade} isOpen={isOpenLike} latestPrice={latestPrice} pnl={pnlNum} pnlPct={pnlPct} />
      <CloseExplanation trade={trade} latestPrice={latestPrice} />

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
                {isOpenLike ? "Unrealized P&L" : "Realized P&L"}
              </div>
              <div className={cn(
                "text-3xl font-bold tabular-nums",
                isProfit ? "text-success" : isLoss ? "text-destructive" : "text-foreground",
              )}>
                {isProfit ? "+" : ""}{formatCurrency(pnlNum)}
              </div>
              {pnlPct != null ? (
                <div className={cn(
                  "mt-1 text-[13px] font-semibold tabular-nums",
                  pnlPct > 0 ? "text-success" : pnlPct < 0 ? "text-destructive" : "text-muted-foreground",
                )}>
                  {pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(2)}%
                </div>
              ) : null}
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
              <StatPill label="Entry" value={formatPrice(trade.entry_price)} />
            ) : null}
            {trade.stop_loss != null ? (
              <StatPill label="Stop loss" value={formatPrice(trade.stop_loss)} color="text-destructive" />
            ) : null}
            {trade.take_profit != null ? (
              <StatPill label="Take profit" value={formatPrice(trade.take_profit)} color="text-success" />
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
            trade.avg_fill_price != null || trade.avg_entry_price != null
              ? { label: "Avg fill",  value: formatPrice(Number(trade.avg_fill_price ?? trade.avg_entry_price)) }
              : null,
            trade.trailing_stop_price != null
              ? { label: "Trail stop", value: formatPrice(trade.trailing_stop_price) }
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

      <TradingViewPosition trade={trade} pnl={pnlNum} pnlPct={pnlPct} />
      <TakeProfitPlanCard trade={trade} />

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

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Brain className="h-4 w-4 text-muted-foreground/50" />
            <CardTitle>Agent discussion</CardTitle>
          </div>
          <CardDescription>Agent votes and reasoning that led to this trade.</CardDescription>
        </CardHeader>
        <CardContent>
          {runs.isLoading || outputs.isLoading ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-32 rounded-xl" />)}
            </div>
          ) : !run || (outputs.data ?? []).length === 0 ? (
            <EmptyState title="No agent trace recorded" />
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {(outputs.data ?? []).map((output) => (
                <AgentTraceCard key={output.id} output={output as unknown as Record<string, unknown>} />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

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

function TradeStatePanel({
  trade,
  isOpen,
  latestPrice,
  pnl,
  pnlPct,
}: {
  trade: Trade;
  isOpen: boolean;
  latestPrice: number | null;
  pnl: number;
  pnlPct: number | null;
}) {
  const filledQty = toNum(trade.filled_quantity) ?? toNum(trade.quantity) ?? 0;
  const entry = toNum(trade.avg_fill_price ?? trade.avg_entry_price ?? trade.entry_price);
  const notional = toNum(trade.notional) ?? (entry != null ? entry * filledQty : null);
  const statusText = trade.status === "closed"
    ? `Closed${trade.close_reason ? ` - ${trade.close_reason.replace(/_/g, " ")}` : ""}`
    : isOpen
      ? "Open and monitoring"
      : trade.status === "pending"
        ? "Waiting for fill"
        : trade.status.replace(/_/g, " ");
  const pnlTone = pnl > 0 ? "text-success" : pnl < 0 ? "text-destructive" : "text-foreground";

  return (
    <div className="grid gap-3 md:grid-cols-4">
      <StateTile
        label="Position"
        value={statusText}
        detail={trade.lifecycle_status.replace(/_/g, " ")}
        tone={trade.status === "closed" ? "muted" : isOpen ? "success" : "warning"}
      />
      <StateTile
        label="Latest price"
        value={latestPrice != null ? formatPrice(latestPrice) : "Waiting"}
        detail={latestPrice != null ? "Live ticker" : "No fresh price"}
      />
      <StateTile
        label="Live P&L"
        value={`${pnl >= 0 ? "+" : ""}${formatCurrency(pnl)}`}
        detail={pnlPct != null ? `${pnlPct >= 0 ? "+" : ""}${pnlPct.toFixed(2)}%` : "percent pending"}
        className={pnlTone}
      />
      <StateTile
        label="Exposure / risk"
        value={notional != null ? formatCurrency(notional) : "-"}
        detail={trade.risk_amount != null ? `Risk ${formatCurrency(Number(trade.risk_amount))}` : "Risk not recorded"}
      />
    </div>
  );
}

function CloseExplanation({ trade, latestPrice }: { trade: Trade; latestPrice: number | null }) {
  if (trade.status !== "closed" && trade.lifecycle_status !== "closed") return null;

  const closeReason = trade.close_reason?.replace(/_/g, " ") ?? "closed";
  const exit = toNum(trade.avg_exit_price ?? trade.exit_price ?? latestPrice);
  const entry = toNum(trade.avg_fill_price ?? trade.avg_entry_price ?? trade.entry_price);
  const risk = toNum(trade.risk_amount);
  const realized = toNum(trade.realized_pnl ?? trade.pnl);
  const isProtective = trade.close_reason === "stop_loss" || trade.close_reason === "trailing_stop" || trade.close_reason === "emergency";
  const title = trade.close_reason === "stop_loss"
    ? "Closed by stop-loss protection"
    : trade.close_reason === "take_profit"
      ? "Closed at take-profit target"
      : trade.close_reason === "trailing_stop"
        ? "Closed by trailing stop"
        : trade.close_reason === "emergency"
          ? "Closed by emergency risk protection"
          : `Closed: ${closeReason}`;
  const detail = [
    trade.close_reason === "stop_loss"
      ? "This is expected risk-control behavior when price reaches the configured stop level."
      : trade.close_reason === "take_profit"
        ? "This is expected profit-taking behavior when price reaches the configured target."
        : isProtective
          ? "This was a protective lifecycle action, not a new agent decision."
          : "The close reason was recorded by the lifecycle engine.",
    entry != null ? `Entry ${formatPrice(entry)}.` : null,
    exit != null ? `Close ${formatPrice(exit)}.` : null,
    risk != null ? `Risk budget ${formatCurrency(risk)}.` : null,
    realized != null ? `Realized P&L ${formatCurrency(realized)}.` : null,
  ].filter(Boolean).join(" ");

  return (
    <div className={cn(
      "rounded-xl border px-4 py-3 text-[13px] leading-relaxed",
      trade.close_reason === "take_profit"
        ? "border-success/25 bg-success/5 text-success"
        : isProtective
          ? "border-destructive/25 bg-destructive/5 text-destructive"
          : "border-border/40 bg-card/50 text-muted-foreground",
    )}>
      <div className="text-[9px] font-semibold uppercase tracking-[0.12em] opacity-70">Close explanation</div>
      <div className="mt-1 font-semibold text-foreground">{title}</div>
      <div className="mt-0.5">{detail}</div>
    </div>
  );
}

function StateTile({
  label,
  value,
  detail,
  tone,
  className,
}: {
  label: string;
  value: string;
  detail: string;
  tone?: "success" | "warning" | "destructive" | "muted";
  className?: string;
}) {
  return (
    <div className={cn(
      "rounded-xl border border-border/40 bg-card/50 px-4 py-3",
      tone === "success" && "border-success/25 bg-success/5",
      tone === "warning" && "border-warning/25 bg-warning/5",
      tone === "destructive" && "border-destructive/25 bg-destructive/5",
      tone === "muted" && "bg-muted/20",
    )}>
      <div className="text-[9px] font-semibold uppercase tracking-[0.12em] text-muted-foreground/60">{label}</div>
      <div className={cn("mt-1 text-[14px] font-semibold text-foreground", className)}>{value}</div>
      <div className="mt-0.5 text-[11px] text-muted-foreground">{detail}</div>
    </div>
  );
}

function TradingViewPosition({
  trade, pnl, pnlPct,
}: {
  trade: Trade;
  pnl: number;
  pnlPct: number | null;
}) {
  const tvSymbol = `${trade.exchange.toUpperCase()}:${trade.symbol.replace("/", "")}`;
  const widgetUrl = `https://s.tradingview.com/widgetembed/?symbol=${encodeURIComponent(tvSymbol)}&interval=1&hidesidetoolbar=1&symboledit=0&saveimage=0&toolbarbg=f1f3f6&studies=[]&theme=dark&style=1&timezone=Etc%2FUTC&withdateranges=1&hideideas=1`;
  const latestPrice = toNum(trade.metadata?.latest_price);
  const isLong = trade.direction === "long" || trade.side === "buy";
  const tpLevels = getTpLevels(getRewardPlan(trade.metadata), trade.metadata)
    .map((level) => {
      const price = toNum(level.price);
      if (price == null) return null;
      return {
        label: String(level.label ?? `TP${String(level.level ?? "")}`),
        price,
        tone: String(level.status ?? "pending") === "hit"
          ? "text-success border-success/40 bg-success/15"
          : "text-success border-success/30 bg-success/10",
      };
    })
    .filter((level): level is { label: string; price: number; tone: string } => level != null);
  const levels = [
    ...(tpLevels.length > 0
      ? tpLevels
      : trade.take_profit != null
        ? [{ label: "TP", price: Number(trade.take_profit), tone: "text-success border-success/30 bg-success/10" }]
        : []),
    { label: "ENTRY", price: Number(trade.entry_price), tone: "text-primary border-primary/30 bg-primary/10" },
    latestPrice != null ? { label: "LAST", price: latestPrice, tone: "text-foreground border-border bg-card/90" } : null,
    trade.stop_loss != null ? { label: "SL", price: Number(trade.stop_loss), tone: "text-destructive border-destructive/30 bg-destructive/10" } : null,
  ].filter(Boolean) as Array<{ label: string; price: number; tone: string }>;

  return (
    <Card className="overflow-hidden">
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <div>
            <CardTitle>Position chart</CardTitle>
            <CardDescription>{tvSymbol}</CardDescription>
          </div>
          <Badge variant={isLong ? "success" : "destructive"}>
            {isLong ? "LONG" : "SHORT"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="relative h-[520px] overflow-hidden rounded-xl border border-border/40 bg-card">
          <iframe
            title={`${tvSymbol} TradingView chart`}
            src={widgetUrl}
            className="h-full w-full"
            allowFullScreen
          />
          <div className="pointer-events-none absolute left-4 top-4 rounded-lg border border-border/50 bg-background/90 px-3 py-2 text-[12px] shadow-lg backdrop-blur">
            <div className="font-mono font-semibold text-foreground">{tvSymbol}</div>
            <div className={cn(
              "mt-1 font-semibold tabular-nums",
              pnl > 0 ? "text-success" : pnl < 0 ? "text-destructive" : "text-muted-foreground",
            )}>
              {pnl >= 0 ? "+" : ""}{formatCurrency(pnl)}
              {pnlPct != null ? ` (${pnlPct >= 0 ? "+" : ""}${pnlPct.toFixed(2)}%)` : ""}
            </div>
          </div>
          <div className="pointer-events-none absolute right-4 top-4 flex flex-col gap-1">
            {levels.map((level) => (
              <div key={level.label} className={cn("rounded-md border px-2 py-1 text-right text-[10px] font-bold tabular-nums shadow-lg backdrop-blur", level.tone)}>
                {level.label} {formatPrice(level.price)}
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

interface Candle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

function useTradeCandles(trade: Trade) {
  return useQuery<Candle[]>({
    queryKey: ["trade-candles", trade.exchange, trade.symbol],
    staleTime: 0,
    refetchInterval: 30_000,
    queryFn: async () => {
      const { data, error } = await supabase
        .from("market_snapshots")
        .select("open_price, high_price, low_price, close_price, captured_at")
        .eq("exchange", trade.exchange)
        .eq("symbol", trade.symbol)
        .eq("timeframe", "1m")
        .order("captured_at", { ascending: false })
        .limit(160);
      if (error) throw error;
      return ((data ?? []) as Record<string, unknown>[])
        .map((row) => ({
          time: String(row.captured_at ?? ""),
          open: Number(row.open_price ?? 0),
          high: Number(row.high_price ?? 0),
          low: Number(row.low_price ?? 0),
          close: Number(row.close_price ?? 0),
        }))
        .filter((row) => row.open > 0 && row.high > 0 && row.low > 0 && row.close > 0)
        .reverse();
    },
  });
}

function PositionSvg({
  candles,
  levels,
  range,
}: {
  candles: Candle[];
  levels: Array<{ label: string; price: number; tone: string }>;
  range: { low: number; high: number } | null;
}) {
  const width = 1000;
  const height = 420;
  const left = 42;
  const right = 152;
  const top = 24;
  const bottom = 36;
  const chartWidth = width - left - right;
  const chartHeight = height - top - bottom;
  const y = (price: number) => {
    if (!range || range.high <= range.low) return top + chartHeight / 2;
    return top + chartHeight - ((price - range.low) / (range.high - range.low)) * chartHeight;
  };
  const x = (idx: number) => left + (idx / Math.max(1, candles.length - 1)) * chartWidth;
  const last = candles.at(-1);

  return (
    <svg className="h-full w-full" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img">
      <rect width={width} height={height} className="fill-background" />
      {[0, 1, 2, 3, 4].map((i) => {
        const gy = top + (i / 4) * chartHeight;
        return <line key={i} x1={left} x2={width - 24} y1={gy} y2={gy} className="stroke-border/40" strokeDasharray="4 8" />;
      })}
      {candles.length > 1 ? (
        <polyline
          fill="none"
          stroke="hsl(var(--primary))"
          strokeWidth="2"
          points={candles.map((c, i) => `${x(i)},${y(c.close)}`).join(" ")}
          vectorEffect="non-scaling-stroke"
        />
      ) : null}
      {candles.map((c, i) => {
        const cx = x(i);
        const up = c.close >= c.open;
        const bodyTop = y(Math.max(c.open, c.close));
        const bodyHeight = Math.max(2, Math.abs(y(c.open) - y(c.close)));
        return (
          <g key={`${c.time}-${i}`}>
            <line x1={cx} x2={cx} y1={y(c.high)} y2={y(c.low)} className={up ? "stroke-success/70" : "stroke-destructive/70"} vectorEffect="non-scaling-stroke" />
            <rect
              x={cx - 2.5}
              y={bodyTop}
              width="5"
              height={bodyHeight}
              rx="1"
              className={up ? "fill-success/80" : "fill-destructive/80"}
            />
          </g>
        );
      })}
      {levels.map((level) => {
        const ly = y(level.price);
        return (
          <g key={level.label}>
            <line x1={left} x2={width - 24} y1={ly} y2={ly} className={cn("stroke-current", level.tone)} strokeWidth="1.5" strokeDasharray={level.label === "ENTRY" ? "0" : "6 6"} vectorEffect="non-scaling-stroke" />
            <foreignObject x={width - right + 12} y={ly - 18} width={right - 24} height="36">
              <div className={cn("rounded-md border px-2 py-1 text-right text-[10px] font-bold tabular-nums shadow-lg backdrop-blur", level.tone)}>
                <div>{level.label}</div>
                <div>{formatPrice(level.price)}</div>
              </div>
            </foreignObject>
          </g>
        );
      })}
      {last ? (
        <text x={left} y={height - 12} className="fill-muted-foreground text-[11px]">
          {new Date(last.time).toLocaleString()}
        </text>
      ) : null}
    </svg>
  );
}

function priceRange(trade: Trade, candles: Candle[] = []): { low: number; high: number } | null {
  const tpPrices = getTpLevels(getRewardPlan(trade.metadata), trade.metadata)
    .map((level) => toNum(level.price))
    .filter((value): value is number => value != null);
  const prices = [
    trade.entry_price,
    trade.stop_loss,
    trade.take_profit,
    trade.exit_price,
    toNum(trade.metadata?.latest_price),
    ...tpPrices,
    ...candles.flatMap((c) => [c.high, c.low]),
  ].map((v) => toNum(v)).filter((v): v is number => v != null && v > 0);
  if (prices.length === 0) return null;
  const low = Math.min(...prices);
  const high = Math.max(...prices);
  if (low === high) return { low: low * 0.98, high: high * 1.02 };
  const pad = (high - low) * 0.18;
  return { low: low - pad, high: high + pad };
}

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

function AgentTraceCard({ output }: { output: Record<string, unknown> }) {
  const payload = (output.output ?? {}) as Record<string, unknown>;
  const name = String(output.agent_name ?? "Agent");
  const displayName = String(output.agent_display_name ?? name);
  const decision = String(output.decision ?? payload.decision ?? "-").replace(/_/g, " ");
  const score = toNum(output.score ?? payload.score);
  const confidence = toNum(output.confidence ?? payload.confidence);
  const reasoning = String(output.reasoning ?? payload.reasoning ?? "");
  const veto = Boolean(output.veto ?? payload.veto);

  return (
    <div className={cn(
      "rounded-xl border bg-card/50 p-4",
      veto ? "border-destructive/30 bg-destructive/5" : "border-border/40",
    )}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[13px] font-semibold text-foreground">{displayName}</div>
          <div className="mt-1 text-[11px] text-muted-foreground">{decision}</div>
        </div>
        {veto ? <Badge variant="destructive" className="text-[10px]">veto</Badge> : null}
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <StatPill label="Score" value={score == null ? "-" : String(Math.round(score))} />
        <StatPill label="Confidence" value={confidence == null ? "-" : `${Math.round(confidence * 100)}%`} />
      </div>
      {reasoning ? (
        <p className="mt-3 line-clamp-5 whitespace-pre-wrap text-[12px] leading-relaxed text-muted-foreground">
          {reasoning}
        </p>
      ) : null}
    </div>
  );
}

function TakeProfitPlanCard({ trade }: { trade: Trade }) {
  const plan = getRewardPlan(trade.metadata);
  const levels = getTpLevels(plan, trade.metadata);
  if (levels.length === 0) return null;

  const selectedR = toNum(plan?.selected_reward_r ?? trade.risk_reward_ratio);
  const realized = toNum(trade.realized_pnl) ?? 0;
  const partials = Array.isArray(trade.metadata?.partial_close_history)
    ? trade.metadata.partial_close_history.length
    : levels.filter((level) => String(level.status ?? "") === "hit").length;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Target className="h-4 w-4 text-muted-foreground/50" />
          <CardTitle>Scaled take-profit plan</CardTitle>
        </div>
        <CardDescription>TP1, TP2, and TP3 partial exits tracked by the position engine.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-3">
          {levels.map((level) => {
            const status = String(level.status ?? "pending");
            const isHit = status === "hit";
            const closePct = normalizePct(toNum(level.close_pct));
            const filledQty = toNum(level.filled_quantity);
            const levelPnl = toNum(level.realized_pnl);
            return (
              <div
                key={`${String(level.label ?? "TP")}-${String(level.level ?? "")}`}
                className={cn(
                  "rounded-xl border px-4 py-3",
                  isHit ? "border-success/25 bg-success/5" : "border-border/40 bg-card/50",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="text-[13px] font-semibold text-foreground">
                    {String(level.label ?? `TP${String(level.level ?? "")}`)}
                  </div>
                  <Badge variant={isHit ? "success" : "secondary"} className="text-[10px]">
                    {status.replace(/_/g, " ")}
                  </Badge>
                </div>
                <div className="mt-2 space-y-1 text-[12px]">
                  <TpMetric label="Price" value={toNum(level.price) != null ? formatPrice(Number(level.price)) : "-"} />
                  <TpMetric label="R" value={toNum(level.r) != null ? `${Number(level.r).toFixed(2)}R` : "-"} />
                  <TpMetric label="Close" value={closePct != null ? `${closePct.toFixed(0)}%` : "-"} />
                  {filledQty != null ? <TpMetric label="Filled" value={formatNumber(filledQty, 8)} /> : null}
                  {levelPnl != null ? (
                    <TpMetric
                      label="Realized"
                      value={formatCurrency(levelPnl)}
                      tone={levelPnl >= 0 ? "success" : "destructive"}
                    />
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <StateTile
            label="Selected R"
            value={selectedR != null ? `${selectedR.toFixed(2)}R` : "-"}
            detail="AI-selected target"
          />
          <StateTile
            label="Partial exits"
            value={String(partials)}
            detail="TP levels filled"
            tone={partials > 0 ? "success" : "muted"}
          />
          <StateTile
            label="Realized from TPs"
            value={`${realized >= 0 ? "+" : ""}${formatCurrency(realized)}`}
            detail="Cumulative realized P&L"
            tone={realized > 0 ? "success" : realized < 0 ? "destructive" : "muted"}
          />
        </div>
      </CardContent>
    </Card>
  );
}

function TpMetric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "success" | "destructive";
}) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground/60">{label}</span>
      <span className={cn(
        "font-mono text-[11px] text-foreground",
        tone === "success" && "text-success",
        tone === "destructive" && "text-destructive",
      )}>
        {value}
      </span>
    </div>
  );
}

function getRewardPlan(metadata: Record<string, unknown> | null | undefined): Record<string, unknown> | null {
  const raw = metadata?.reward_plan;
  return raw && typeof raw === "object" && !Array.isArray(raw)
    ? raw as Record<string, unknown>
    : null;
}

function getTpLevels(
  plan: Record<string, unknown> | null,
  metadata: Record<string, unknown> | null | undefined,
): Record<string, unknown>[] {
  const fromPlan = plan?.levels;
  if (Array.isArray(fromPlan)) return fromPlan.filter(isRecord);
  const fromMetadata = metadata?.tp_plan;
  return Array.isArray(fromMetadata) ? fromMetadata.filter(isRecord) : [];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function normalizePct(value: number | null): number | null {
  if (value == null) return null;
  return value <= 1 ? value * 100 : value;
}

function toNum(value: unknown): number | null {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
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
