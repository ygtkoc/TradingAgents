"use client";

import { type ColumnDef, DataTable, EmptyState } from "@ta/ui";
import { cn, formatCurrency, formatRelative } from "@ta/utils";
import type { Trade } from "@ta/types";
import { ArrowUpRight, ArrowDownRight, TrendingDown, TrendingUp } from "lucide-react";
import { useRouter } from "next/navigation";

import { useTrades } from "@/lib/hooks/queries/use-trades";

const columns: ColumnDef<Trade, unknown>[] = [
  {
    header: "Symbol",
    cell: ({ row }) => (
      <div className="flex flex-col gap-0.5">
        <span className="font-mono text-[13px] font-semibold text-foreground">
          {row.original.symbol}
        </span>
        <span className="text-[10px] uppercase text-muted-foreground/50">
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
          "flex items-center gap-0.5 text-[11px] font-semibold",
          isLong ? "text-success" : "text-destructive",
        )}>
          {isLong ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
          {isLong ? "L" : "S"}
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
          "flex items-center gap-1 text-[11px] font-medium",
          s === "open" ? "text-primary" : s === "closed" ? "text-muted-foreground/60" : "text-muted-foreground/40",
        )}>
          {s === "open" && <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />}
          {s}
        </div>
      );
    },
  },
  {
    header: "P&L",
    cell: ({ row }) => {
      const t   = row.original;
      const pnl = t.realized_pnl ?? t.unrealized_pnl ?? 0;
      return (
        <div className={cn(
          "flex items-center gap-0.5 font-semibold tabular-nums text-[13px]",
          pnl > 0 ? "text-success" : pnl < 0 ? "text-destructive" : "text-foreground",
        )}>
          {pnl > 0 ? <ArrowUpRight className="h-3.5 w-3.5" /> : pnl < 0 ? <ArrowDownRight className="h-3.5 w-3.5" /> : null}
          {pnl >= 0 ? "+" : ""}{formatCurrency(pnl)}
        </div>
      );
    },
  },
  {
    header: "When",
    cell: ({ row }) => (
      <span className="text-[11px] text-muted-foreground/60">
        {formatRelative(row.original.created_at)}
      </span>
    ),
  },
];

interface Props {
  limit?:  number;
  status?: "open" | "closed";
  mode?:   "paper" | "live" | "shadow";
}

export function RecentTradesTable({ limit = 10, status, mode }: Props) {
  const router = useRouter();
  const { data, error, isLoading, isError } = useTrades({ limit, status, mode });

  if (isError) {
    console.error("dashboard.trades.section.failed", { limit, error });
    return <EmptyState title="Trades temporarily unavailable" />;
  }

  return (
    <DataTable
      columns={columns}
      data={data ?? []}
      loading={isLoading}
      onRowClick={(t) => router.push(`/trades/${t.id}`)}
      empty={<EmptyState title="No trades yet" description="Trades appear as the agent pipeline opens positions." />}
      pageSize={limit}
    />
  );
}
