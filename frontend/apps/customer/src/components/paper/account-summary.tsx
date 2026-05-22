"use client";

import { Badge } from "@ta/ui";
import { cn, formatCurrency, formatRelative } from "@ta/utils";
import type { Trade } from "@ta/types";
import {
  Activity, ArrowDownRight, ArrowUpRight, Bot, CheckCircle2,
  ChevronRight, Pause, PowerOff, RefreshCw, TrendingUp, XCircle,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { PaperAccount } from "@/lib/hooks/queries/use-paper-account";
import { usePaperAccount }   from "@/lib/hooks/queries/use-paper-account";
import { useBots }           from "@/lib/hooks/queries/use-bots";
import { useDecisions }      from "@/lib/hooks/queries/use-decisions";
import { useTrades }         from "@/lib/hooks/queries/use-trades";
import { useUserSettings }   from "@/lib/hooks/queries/use-user-settings";

import { AccountControls }   from "./account-controls";

const STATUS_META = {
  active:   { icon: Activity,  color: "text-success", bg: "bg-success/12 border-success/20",    glow: "shadow-[0_0_20px_hsl(158,72%,42%,0.15)]" },
  paused:   { icon: Pause,     color: "text-warning", bg: "bg-warning/12 border-warning/20",    glow: "" },
  inactive: { icon: PowerOff,  color: "text-muted-foreground", bg: "bg-secondary border-border", glow: "" },
} as const;

interface Props { account: PaperAccount }

export function AccountSummary({ account }: Props) {
  const { isFetching } = usePaperAccount();

  const status = (account.status === "active" || account.status === "paused" || account.status === "inactive")
    ? account.status : "inactive";

  const { icon: StatusIcon, color, bg, glow } = STATUS_META[status];

  const totalBalance = safeNum(account.balance);
  const reservedBalance = safeNum(account.reserved_balance);
  const availableBalance = safeNum(
    account.available_balance ?? totalBalance - reservedBalance,
  );
  const rawRealized = safeNum(account.realized_pnl);
  const rawUnrealized = safeNum(account.unrealized_pnl);
  const start     = safeNum(account.starting_balance) || 1;

  const { data: openTrades }   = useTrades({ status: "open",  mode: "paper" });
  const { data: closedTrades } = useTrades({ status: "closed", mode: "paper" });
  const { data: allDecisions } = useDecisions({ limit: 100 });
  const { data: bots }         = useBots();
  const { data: settings }     = useUserSettings();
  const livePrices = useLivePrices(openTrades ?? []);

  const tradeUnrealized = (openTrades ?? []).reduce((sum, trade) =>
    sum + calcUnrealizedPnl(trade, livePrices), 0);
  const tradeRealized = (closedTrades ?? []).reduce((sum, trade) =>
    sum + safeNum(trade.realized_pnl ?? trade.pnl), 0);

  // Paper accounts may briefly report 0 P&L while trades already have P&L values.
  // Prefer account totals when they are non-zero, but fall back to trade-derived totals
  // when the account reports zero and trades clearly have non-zero P&L.
  const hasOpenTrades = (openTrades ?? []).length > 0;
  const realized = rawRealized === 0 && tradeRealized !== 0 ? tradeRealized : rawRealized;
  const unrealized = hasOpenTrades ? tradeUnrealized : rawUnrealized;

  const equity    = totalBalance + unrealized;
  const change    = ((equity - start) / start) * 100;
  const isPositive = change >= 0;

  const openTradeCount  = openTrades?.length ?? 0;
  const approvedCount   = allDecisions?.filter((d) =>
    d.approval_status === "auto_approved" || d.approval_status === "approved"
  ).length ?? 0;
  const rejectedCount   = allDecisions?.filter((d) =>
    d.approval_status === "rejected"
  ).length ?? 0;

  const warmingUpCount = (bots ?? []).filter(
    (b) => b.mode === "paper" && !b.is_archived && b.warmup_status !== "ready",
  ).length;

  const riskPct   = settings?.default_risk_per_trade_pct ?? 2;

  return (
    <div className={cn(
      "relative overflow-hidden rounded-2xl border bg-card/80 backdrop-blur-sm",
      status === "active" ? "border-success/20" : "border-border/50",
      glow,
    )}>
      {/* Background glow gradient */}
      <div className={cn(
        "pointer-events-none absolute inset-0",
        status === "active"
          ? "bg-[radial-gradient(ellipse_at_top_right,hsl(158_72%_42%/0.06),transparent_60%)]"
          : "bg-[radial-gradient(ellipse_at_top_right,hsl(var(--primary)/0.05),transparent_60%)]",
      )} />

      {/* Top section: status + equity hero */}
      <div className="relative p-6">
        <div className="flex items-start justify-between">
          {/* Left: equity hero */}
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-[12px] text-muted-foreground">
              <span className="font-medium uppercase tracking-[0.12em]">Paper account</span>
              {isFetching && (
                <RefreshCw className="h-3 w-3 animate-spin opacity-40" aria-label="Refreshing" />
              )}
            </div>
            <div className="flex items-baseline gap-3">
              <span className="text-3xl font-bold tabular-nums tracking-tight text-foreground">
                {formatCurrency(equity)}
              </span>
              <span className={cn(
                "flex items-center gap-0.5 text-sm font-semibold tabular-nums",
                isPositive ? "text-success" : "text-destructive",
              )}>
                {isPositive ? <ArrowUpRight className="h-4 w-4" /> : <ArrowDownRight className="h-4 w-4" />}
                {isPositive ? "+" : ""}{change.toFixed(2)}%
              </span>
            </div>
            <div className="text-[12px] text-muted-foreground">
              {status === "active"   && account.started_at && `Running ${formatRelative(account.started_at)}`}
              {status === "paused"   && account.paused_at  && `Paused ${formatRelative(account.paused_at)}`}
              {status === "inactive" && "Ready to start — configure bots on the Bots page"}
            </div>
          </div>

          {/* Right: status badge */}
          <div className={cn(
            "flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-[12px] font-semibold",
            bg,
          )}>
            {status === "active" ? (
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-60" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-success" />
              </span>
            ) : (
              <StatusIcon className={cn("h-3.5 w-3.5", color)} />
            )}
            <span className={color}>{status}</span>
          </div>
        </div>
      </div>

      {/* Divider */}
      <div className="mx-6 border-t border-border/30" />

      {/* Stats grid */}
      <div className="relative grid grid-cols-2 gap-px bg-border/20 sm:grid-cols-3 lg:grid-cols-9">
        {[
          { label: "Available",  value: formatCurrency(availableBalance), icon: null },
          { label: "Total",      value: formatCurrency(totalBalance),     icon: null },
          { label: "In trades",  value: formatCurrency(reservedBalance),  icon: null },
          { label: "Realized",   value: formatCurrency(realized), icon: realized >= 0 ? ArrowUpRight : ArrowDownRight,
            tone: realized > 0 ? "pos" : realized < 0 ? "neg" : null },
          { label: "Unrealized", value: formatCurrency(unrealized), icon: null,
            tone: unrealized > 0 ? "pos" : unrealized < 0 ? "neg" : null },
          { label: "Open trades", value: String(openTradeCount), icon: TrendingUp },
          { label: "Risk/trade",  value: `${riskPct}%`,          icon: null },
          { label: "Approved",    value: String(approvedCount),  icon: CheckCircle2, tone: "pos" as const },
          { label: "Rejected",    value: String(rejectedCount),  icon: XCircle,
            tone: rejectedCount > 0 ? "neg" : null },
        ].map(({ label, value, icon: Icon, tone }) => (
          <div key={label} className="flex flex-col gap-0.5 bg-card/60 px-4 py-3 backdrop-blur-sm">
            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground/60">
              {label}
            </div>
            <div className={cn(
              "flex items-center gap-1 text-[15px] font-bold tabular-nums",
              tone === "pos" && "text-success",
              tone === "neg" && "text-destructive",
              !tone          && "text-foreground",
            )}>
              {Icon && <Icon className="h-3.5 w-3.5 shrink-0 opacity-60" />}
              {value}
            </div>
          </div>
        ))}
      </div>

      {/* Warming up notice */}
      {warmingUpCount > 0 ? (
        <div className="relative mx-6 mb-2 mt-3 flex items-center gap-2 rounded-lg border border-warning/20 bg-warning/5 px-3 py-2 text-[12px] text-warning">
          <Bot className="h-3.5 w-3.5 shrink-0" />
          <span>{warmingUpCount} bot{warmingUpCount > 1 ? "s" : ""} warming up — collecting historical candles</span>
          <ChevronRight className="ml-auto h-3 w-3 opacity-50" />
        </div>
      ) : null}

      {/* Controls */}
      <div className="relative p-6 pt-4">
        <AccountControls account={account} />
      </div>
    </div>
  );
}

function safeNum(value: unknown): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function normalizeSymbol(symbol: string): string {
  return symbol.replace("/", "").toUpperCase();
}

function useLivePrices(trades: Trade[]): Map<string, number> {
  const [prices, setPrices] = useState<Map<string, number>>(new Map());
  const symbols = useMemo(
    () => Array.from(new Set(trades.map((trade) => normalizeSymbol(trade.symbol)).filter(Boolean))).sort(),
    [trades],
  );
  const streams = symbols.map((symbol) => `${symbol.toLowerCase()}@ticker`).join("/");

  useEffect(() => {
    if (symbols.length === 0 || !streams) {
      setPrices(new Map());
      return;
    }

    let closed = false;
    const socket = new WebSocket(`wss://stream.binance.com:9443/stream?streams=${streams}`);

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(String(event.data)) as { data?: { s?: string; c?: string } };
        const symbol = payload.data?.s;
        const price = Number(payload.data?.c);
        if (!symbol || !Number.isFinite(price) || price <= 0 || closed) return;
        setPrices((prev) => {
          const next = new Map(prev);
          next.set(symbol, price);
          return next;
        });
      } catch {
        // Ignore malformed ticker frames; the polling trade query remains the fallback.
      }
    };

    return () => {
      closed = true;
      socket.close();
    };
  }, [streams, symbols.length]);

  return prices;
}

function calcUnrealizedPnl(trade: Trade, prices: Map<string, number>): number {
  const entry = safeNum(trade.avg_fill_price ?? trade.avg_entry_price ?? trade.entry_price);
  const qty = safeNum(trade.filled_quantity ?? trade.quantity);
  const livePrice = prices.get(normalizeSymbol(trade.symbol));
  if (entry > 0 && qty > 0 && livePrice && livePrice > 0) {
    return trade.direction === "short"
      ? (entry - livePrice) * qty
      : (livePrice - entry) * qty;
  }
  return safeNum(trade.unrealized_pnl ?? trade.pnl);
}
