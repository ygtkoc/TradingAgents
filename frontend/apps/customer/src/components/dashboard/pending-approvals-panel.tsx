"use client";

import {
  Button, Card, CardContent, CardDescription, CardHeader, CardTitle, EmptyState, Skeleton,
} from "@ta/ui";
import { cn, formatRelative } from "@ta/utils";
import { Check, Clock, ShieldAlert, TrendingDown, TrendingUp, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { formatScoreCell } from "@/lib/decisions/summary";
import { useDecisionMutations } from "@/lib/hooks/mutations/use-decision-mutations";
import { usePendingDecisions } from "@/lib/hooks/queries/use-decisions";

export function PendingApprovalsPanel() {
  const router = useRouter();
  const pending = usePendingDecisions();
  const { approve, reject } = useDecisionMutations();
  const rows = pending.data ?? [];

  return (
    <Card className={cn(rows.length > 0 && "border-warning/30 bg-warning/5")}>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-warning" />
              Pending approvals
            </CardTitle>
            <CardDescription>Manual review decisions waiting for your action.</CardDescription>
          </div>
          <Link href="/decisions">
            <Button size="sm" variant="outline">All decisions</Button>
          </Link>
        </div>
      </CardHeader>
      <CardContent>
        {pending.isLoading ? (
          <Skeleton className="h-36 w-full rounded-lg" />
        ) : pending.isError ? (
          <EmptyState title="Pending approvals unavailable" />
        ) : rows.length === 0 ? (
          <EmptyState title="No approvals waiting" description="Manual review decisions will appear here." />
        ) : (
          <div className="space-y-2">
            {rows.slice(0, 5).map((decision) => {
              const isLong = decision.final_decision.includes("open_long");
              const isShort = decision.final_decision.includes("open_short");
              const busy =
                (approve.isPending && approve.variables === decision.id) ||
                (reject.isPending && reject.variables?.decisionId === decision.id);

              return (
                <div
                  key={decision.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => router.push(`/decisions/${decision.id}`)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") router.push(`/decisions/${decision.id}`);
                  }}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border/40 bg-card/70 px-3 py-2 text-[13px] transition hover:bg-accent/40"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-semibold text-foreground">{decision.symbol}</span>
                      <span className={cn(
                        "flex items-center gap-1 text-[11px] font-semibold",
                        isLong ? "text-success" : isShort ? "text-destructive" : "text-muted-foreground",
                      )}>
                        {isLong ? <TrendingUp className="h-3 w-3" /> : isShort ? <TrendingDown className="h-3 w-3" /> : <ShieldAlert className="h-3 w-3" />}
                        {decision.final_decision.replace(/_/g, " ")}
                      </span>
                    </div>
                    <div className="mt-0.5 flex items-center gap-2 text-[11px] text-muted-foreground">
                      <span>Score {formatScoreCell(decision)}</span>
                      <span>{formatRelative(decision.created_at)}</span>
                    </div>
                  </div>

                  <div className="flex shrink-0 items-center gap-1" onClick={(event) => event.stopPropagation()}>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 border-success/30 px-2 text-success hover:bg-success/10"
                      disabled={busy}
                      onClick={() => approve.mutate(decision.id)}
                    >
                      <Check className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 px-2 text-muted-foreground hover:text-destructive"
                      disabled={busy}
                      onClick={() => {
                        const reason = window.prompt("Reason for rejection?")?.trim();
                        if (reason) reject.mutate({ decisionId: decision.id, reason });
                      }}
                    >
                      <X className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
