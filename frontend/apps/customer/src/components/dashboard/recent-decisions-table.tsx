"use client";

import { type ColumnDef, DataTable, EmptyState } from "@ta/ui";
import { cn, formatRelative } from "@ta/utils";
import type { TradeDecision } from "@ta/types";
import {
  CheckCircle2, Clock, ListChecks, ShieldAlert, TrendingDown, TrendingUp, Zap,
} from "lucide-react";
import { useRouter } from "next/navigation";

import { formatScoreCell, getDecisionConfidence } from "@/lib/decisions/summary";
import { useDecisions } from "@/lib/hooks/queries/use-decisions";

const columns: ColumnDef<TradeDecision, unknown>[] = [
  {
    header: "Symbol",
    cell: ({ row }) => (
      <span className="font-mono text-[13px] font-semibold text-foreground">
        {row.original.symbol}
      </span>
    ),
  },
  {
    header: "Decision",
    cell: ({ row }) => {
      const d = row.original.final_decision;
      const isLong   = d.includes("open_long");
      const isShort  = d.includes("open_short");
      const isReject = d === "reject";
      return (
        <div className={cn(
          "flex items-center gap-1 text-[11px] font-semibold",
          isLong   ? "text-success"
          : isShort  ? "text-destructive"
          : isReject ? "text-destructive/70"
          : "text-muted-foreground",
        )}>
          {isLong   && <TrendingUp   className="h-3 w-3" />}
          {isShort  && <TrendingDown className="h-3 w-3" />}
          {isReject && <ShieldAlert  className="h-3 w-3" />}
          {!isLong && !isShort && !isReject && <Zap className="h-3 w-3" />}
          {d.replace(/_/g, " ")}
        </div>
      );
    },
  },
  {
    header: "Score",
    cell: ({ row }) => {
      const raw = formatScoreCell(row.original);
      const n   = parseFloat(String(raw));
      return (
        <span className={cn(
          "tabular-nums text-[13px] font-semibold",
          n > 0 ? "text-success" : n < 0 ? "text-destructive" : "text-foreground",
        )}>
          {raw}
        </span>
      );
    },
  },
  {
    header: "Conf.",
    cell: ({ row }) => {
      const confRaw = getDecisionConfidence(row.original);
      const conf = confRaw != null ? Number(confRaw) : null;
      return conf != null && Number.isFinite(conf) ? (
        <div className="flex items-center gap-1">
          <div className="h-1 w-10 overflow-hidden rounded-full bg-border/40">
            <div className="h-full rounded-full bg-primary/60" style={{ width: `${Math.round(conf * 100)}%` }} />
          </div>
          <span className="text-[10px] tabular-nums text-muted-foreground/60">{Math.round(conf * 100)}%</span>
        </div>
      ) : <span className="text-[11px] text-muted-foreground/40">—</span>;
    },
  },
  {
    header: "Approval",
    cell: ({ row }) => {
      const s = row.original.approval_status;
      if (s === "approved" || s === "auto_approved") return (
        <div className="flex items-center gap-1 text-[11px] font-semibold text-success">
          <CheckCircle2 className="h-3 w-3" /> OK
        </div>
      );
      if (s === "rejected") return (
        <div className="flex items-center gap-1 text-[11px] font-semibold text-destructive">
          <ShieldAlert className="h-3 w-3" /> Reject
        </div>
      );
      if (s === "pending") return (
        <div className="flex items-center gap-1 text-[11px] font-semibold text-warning">
          <Clock className="h-3 w-3 animate-pulse" /> Pending
        </div>
      );
      return <span className="text-[11px] text-muted-foreground/50">{s}</span>;
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

interface Props { limit?: number }

export function RecentDecisionsTable({ limit = 10 }: Props) {
  const router = useRouter();
  const { data, error, isLoading, isError } = useDecisions({ limit });

  if (isError) {
    console.error("dashboard.decisions.section.failed", { limit, error });
    return <EmptyState title="Decisions temporarily unavailable" />;
  }

  return (
    <DataTable
      columns={columns}
      data={data ?? []}
      loading={isLoading}
      onRowClick={(d) => router.push(`/decisions/${d.id}`)}
      empty={
        <EmptyState
          icon={ListChecks}
          title="No decisions yet"
          description="Agent pipeline outcomes will appear here once bots are active."
        />
      }
      pageSize={limit}
    />
  );
}
