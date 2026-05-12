"use client";

import {
  Badge,
  Button,
  type ColumnDef,
  DataTable,
  EmptyState,
} from "@ta/ui";
import { cn, formatRelative } from "@ta/utils";
import type { TradeDecision } from "@ta/types";
import {
  Check, CheckCircle2, Clock, ListChecks, ShieldAlert,
  TrendingDown, TrendingUp, X, Zap,
} from "lucide-react";
import { useRouter } from "next/navigation";

import { formatConfidenceCell, formatScoreCell, getDecisionConfidence } from "@/lib/decisions/summary";
import { useDecisionMutations } from "@/lib/hooks/mutations/use-decision-mutations";
import { useDecisions }          from "@/lib/hooks/queries/use-decisions";

function DecisionBadge({ decision }: { decision: string }) {
  const isLong  = decision.includes("open_long");
  const isShort = decision.includes("open_short");
  const isReject = decision === "reject";
  const isWait   = decision === "wait";

  if (isLong)   return (
    <div className="flex items-center gap-1 text-[11px] font-semibold text-success">
      <TrendingUp className="h-3 w-3" /> Long
    </div>
  );
  if (isShort)  return (
    <div className="flex items-center gap-1 text-[11px] font-semibold text-destructive">
      <TrendingDown className="h-3 w-3" /> Short
    </div>
  );
  if (isReject) return (
    <div className="flex items-center gap-1 text-[11px] font-semibold text-destructive/70">
      <ShieldAlert className="h-3 w-3" /> Reject
    </div>
  );
  if (isWait)   return (
    <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
      <Zap className="h-3 w-3" /> Wait
    </div>
  );
  return <span className="text-[11px] text-muted-foreground">{decision.replace(/_/g, " ")}</span>;
}

function ApprovalChip({ status }: { status: string }) {
  if (status === "auto_approved" || status === "approved") return (
    <div className="flex items-center gap-1 text-[11px] font-semibold text-success">
      <CheckCircle2 className="h-3 w-3" /> Approved
    </div>
  );
  if (status === "rejected") return (
    <div className="flex items-center gap-1 text-[11px] font-semibold text-destructive">
      <ShieldAlert className="h-3 w-3" /> Rejected
    </div>
  );
  if (status === "pending") return (
    <div className="flex items-center gap-1 text-[11px] font-semibold text-warning">
      <Clock className="h-3 w-3 animate-pulse" /> Pending
    </div>
  );
  return <span className="text-[11px] text-muted-foreground">{status}</span>;
}

export function DecisionsTable() {
  const router  = useRouter();
  const decisions = useDecisions({ limit: 200 });
  const { approve, reject } = useDecisionMutations();

  const columns: ColumnDef<TradeDecision, unknown>[] = [
    {
      header: "Symbol",
      cell: ({ row }) => (
        <div className="flex flex-col gap-0.5">
          <span className="font-mono text-[13px] font-semibold text-foreground">
            {row.original.symbol}
          </span>
          <span className="text-[10px] text-muted-foreground/50 uppercase">
            {row.original.mode}
          </span>
        </div>
      ),
    },
    {
      header: "Decision",
      cell: ({ row }) => <DecisionBadge decision={row.original.final_decision} />,
    },
    {
      header: "Score",
      cell: ({ row }) => {
        const raw = formatScoreCell(row.original);
        const n   = typeof raw === "string" ? parseFloat(raw) : null;
        return (
          <span className={cn(
            "tabular-nums text-[13px] font-semibold",
            n != null && n > 0 ? "text-success"
            : n != null && n < 0 ? "text-destructive"
            : "text-foreground",
          )}>
            {raw}
          </span>
        );
      },
    },
    {
      header: "Confidence",
      cell: ({ row }) => {
        const confRaw = getDecisionConfidence(row.original);
        const conf = confRaw != null ? Number(confRaw) : null;
        return conf != null && Number.isFinite(conf) ? (
          <div className="flex items-center gap-1">
            <div className="h-1 w-12 overflow-hidden rounded-full bg-border/40">
              <div
                className="h-full rounded-full bg-primary/60"
                style={{ width: `${Math.round(conf * 100)}%` }}
              />
            </div>
            <span className="text-[11px] tabular-nums text-muted-foreground">
              {Math.round(conf * 100)}%
            </span>
          </div>
        ) : (
          <span className="text-[11px] text-muted-foreground/40">—</span>
        );
      },
    },
    {
      header: "Approval",
      cell: ({ row }) => {
        const d = row.original;
        const warmingUp = d.metadata?.warming_up === true;
        return (
          <div className="flex items-center gap-1.5">
            <ApprovalChip status={d.approval_status} />
            {warmingUp && (
              <Badge variant="warning" className="text-[10px] gap-1">
                <Clock className="h-2.5 w-2.5" /> warmup
              </Badge>
            )}
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
    {
      header: "Actions",
      cell: ({ row }) => {
        const d = row.original;
        if (d.approval_status !== "pending") return null;
        const busy =
          (approve.isPending && approve.variables === d.id) ||
          (reject.isPending  && reject.variables?.decisionId === d.id);
        return (
          <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
            <Button
              size="sm"
              variant="outline"
              className="h-7 w-7 p-0 border-success/30 text-success hover:bg-success/10"
              disabled={busy}
              onClick={() => approve.mutate(d.id)}
            >
              <Check className="h-3.5 w-3.5" />
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
              disabled={busy}
              onClick={() => {
                const reason = window.prompt("Reason for rejection?")?.trim();
                if (reason) reject.mutate({ decisionId: d.id, reason });
              }}
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        );
      },
    },
  ];

  if (decisions.isError) {
    return (
      <EmptyState
        icon={ListChecks}
        title="Decisions temporarily unavailable"
        description="We could not load decisions right now."
      />
    );
  }

  return (
    <DataTable
      columns={columns}
      data={decisions.data ?? []}
      loading={decisions.isLoading}
      onRowClick={(d) => router.push(`/decisions/${d.id}`)}
      empty={
        <EmptyState
          icon={ListChecks}
          title="No decisions yet"
          description="The autonomous engine will log decisions here as signals are processed."
        />
      }
    />
  );
}
