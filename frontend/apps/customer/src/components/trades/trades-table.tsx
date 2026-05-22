"use client";

import {
  type ColumnDef,
  DataTable,
  EmptyState,
  ErrorState,
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@ta/ui";
import { cn, formatCurrency, formatRelative } from "@ta/utils";
import type { Trade, TradeMode } from "@ta/types";
import { ArrowDownRight, ArrowUpRight, TrendingDown, TrendingUp } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { useTrades } from "@/lib/hooks/queries/use-trades";
import { formatPrice } from "@/lib/format-price";

type StatusFilter = "all" | Trade["status"];
type ModeFilter   = "all" | TradeMode;

const columns: ColumnDef<Trade, unknown>[] = [
  {
    header: "Symbol",
    cell: ({ row }) => (
      <div className="flex flex-col gap-0.5">
        <span className="font-mono text-[13px] font-semibold text-foreground">
          {row.original.symbol}
        </span>
        <span className="text-[10px] text-muted-foreground/60 uppercase">
          {row.original.mode}
        </span>
      </div>
    ),
  },
  {
    header: "Side",
    cell: ({ row }) => {
      const isLong = row.original.direction === "long";
      return (
        <div className={cn(
          "flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold w-fit",
          isLong
            ? "bg-success/12 text-success border border-success/20"
            : "bg-destructive/12 text-destructive border border-destructive/20",
        )}>
          {isLong ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
          {isLong ? "LONG" : "SHORT"}
        </div>
      );
    },
  },
  {
    header: "Status",
    cell: ({ row }) => {
      const s = row.original.status;
      return (
        <div className={cn(
          "flex items-center gap-1 text-[11px] font-semibold",
          s === "open"       ? "text-primary"
          : s === "closed"   ? "text-muted-foreground"
          : s === "pending"  ? "text-warning"
          : s === "failed" || s === "cancelled" ? "text-destructive/80"
          : s === "simulated" ? "text-muted-foreground/80"
          : "text-muted-foreground",
        )}>
          {s === "open" && (
            <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
          )}
          {s}
        </div>
      );
    },
  },
  {
    header: "Entry",
    cell: ({ row }) => {
      const t = row.original;
      return t.entry_price
        ? <span className="tabular-nums text-[13px]">{formatPrice(Number(t.entry_price))}</span>
        : <span className="text-muted-foreground">—</span>;
    },
  },
  {
    header: "Notional",
    cell: ({ row }) => {
      const t = row.original;
      const n = t.notional != null
        ? Number(t.notional)
        : t.entry_price && t.quantity
          ? Number(t.entry_price) * Number(t.quantity)
          : null;
      return n != null
        ? <span className="tabular-nums text-[13px]">{formatCurrency(n)}</span>
        : <span className="text-muted-foreground">—</span>;
    },
  },
  {
    header: "R",
    cell: ({ row }) => {
      const t = row.original;
      if (t.r_multiple == null) {
        return t.risk_amount != null
          ? (
            <span className="inline-flex flex-col tabular-nums text-[11px] font-semibold text-foreground">
              <span>1R</span>
              <span className="text-muted-foreground/70">{formatCurrency(Number(t.risk_amount))}</span>
            </span>
          )
          : <span className="text-[11px] text-muted-foreground/50">—</span>;
      }
      const r = Number(t.r_multiple);
      return (
        <span className={cn(
          "inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-[11px] font-bold",
          r > 0
            ? "bg-success/12 text-success border border-success/20"
            : r < 0
              ? "bg-destructive/12 text-destructive border border-destructive/20"
              : "text-muted-foreground",
        )}>
          {r > 0 ? <ArrowUpRight className="h-3 w-3" /> : r < 0 ? <ArrowDownRight className="h-3 w-3" /> : null}
          {r >= 0 ? "+" : ""}{r.toFixed(2)}R
        </span>
      );
    },
  },
  {
    header: "P&L",
    cell: ({ row }) => {
      const t   = row.original;
      const raw = t.status === "open"
        ? t.unrealized_pnl ?? t.pnl
        : t.realized_pnl ?? t.pnl;
      if (raw == null) return <span className="text-muted-foreground">—</span>;
      const pnl = Number(raw);
      const pct = t.pnl_pct != null ? Number(t.pnl_pct) : null;
      return (
        <div className={cn(
          "flex flex-col tabular-nums text-[13px] font-semibold",
          pnl > 0 ? "text-success" : pnl < 0 ? "text-destructive" : "text-foreground",
        )}>
          <span>{pnl >= 0 ? "+" : ""}{formatCurrency(pnl)}</span>
          {pct != null ? (
            <span className="text-[10px] font-medium opacity-70">
              {pct >= 0 ? "+" : ""}{pct.toFixed(2)}%
            </span>
          ) : null}
        </div>
      );
    },
  },
  {
    header: "Opened",
    cell: ({ row }) => (
      <span className="text-[11px] text-muted-foreground/70">
        {formatRelative(row.original.created_at)}
      </span>
    ),
  },
];

export function TradesTable() {
  const router = useRouter();
  const [status, setStatus] = useState<StatusFilter>("all");
  const [mode, setMode]     = useState<ModeFilter>("all");

  const { data, isLoading, isError, refetch } = useTrades({
    status: status === "all" ? undefined : status,
    mode:   mode   === "all" ? undefined : mode,
    limit:  500,
  });

  if (isError) return <ErrorState onRetry={() => void refetch()} />;

  return (
    <div className="space-y-4">
      {/* Filter row */}
      <div className="flex flex-wrap items-center gap-2">
        <Select value={status} onValueChange={(v) => setStatus(v as StatusFilter)}>
          <SelectTrigger className="h-8 w-[140px] rounded-lg border-border/60 bg-card/60 text-[12px]">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All status</SelectItem>
          <SelectItem value="pending">Pending</SelectItem>
          <SelectItem value="open">Open</SelectItem>
          <SelectItem value="closed">Closed</SelectItem>
          <SelectItem value="failed">Failed</SelectItem>
          <SelectItem value="cancelled">Cancelled</SelectItem>
          <SelectItem value="simulated">Simulated</SelectItem>
        </SelectContent>
      </Select>
        <Select value={mode} onValueChange={(v) => setMode(v as ModeFilter)}>
          <SelectTrigger className="h-8 w-[130px] rounded-lg border-border/60 bg-card/60 text-[12px]">
            <SelectValue placeholder="Mode" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All modes</SelectItem>
            <SelectItem value="paper">Paper</SelectItem>
            <SelectItem value="shadow">Shadow</SelectItem>
            <SelectItem value="live">Live</SelectItem>
          </SelectContent>
        </Select>

        {data && (
          <span className="text-[11px] text-muted-foreground/50 ml-1">
            {data.length} trade{data.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      <DataTable
        columns={columns}
        data={data ?? []}
        loading={isLoading}
        onRowClick={(t) => router.push(`/trades/${t.id}`)}
        empty={
          <EmptyState
            title="No trades match"
            description="Adjust the filters above or wait for the autonomous engine to open positions."
          />
        }
      />
    </div>
  );
}
