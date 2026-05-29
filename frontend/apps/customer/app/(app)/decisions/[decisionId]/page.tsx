"use client";

import {
  Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle,
  EmptyState, ErrorState, PageHeader, ProductPage, Skeleton,
} from "@ta/ui";
import { cn, formatCurrency, formatDateTime, formatRelative } from "@ta/utils";
import {
  ArrowLeft, Bot, Brain, ChevronRight, Clock, Shield, ShieldAlert,
  ShieldCheck, Sparkles, Target, TrendingUp, Zap,
} from "lucide-react";
import type { Trade, TradeDecision } from "@ta/types";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import {
  formatConfidenceCell, formatScoreCell,
  getDecisionConfidence, getDecisionRationale,
  getDecisionReasoning, getDecisionScore,
} from "@/lib/decisions/summary";
import { formatPrice } from "@/lib/format-price";
import {
  useAgentOutputs, useDecisionAgentRuns, useSignal,
  useTradeEventsForDecision, useTradeForDecision,
} from "@/lib/hooks/queries/use-decision-detail";
import { useDecision } from "@/lib/hooks/queries/use-decisions";

// ── Agent icon + color map ───────────────────────────────────────────────────
const AGENT_META: Record<string, { icon: typeof Bot; color: string; label: string }> = {
  technical:  { icon: TrendingUp,  color: "text-primary  bg-primary/10  border-primary/20",  label: "Technical Analysis" },
  price:      { icon: Sparkles,    color: "text-violet-400 bg-violet-400/10 border-violet-400/20", label: "Price Action" },
  risk:       { icon: Shield,      color: "text-warning  bg-warning/10  border-warning/20",  label: "Risk Manager" },
  sentiment:  { icon: Brain,       color: "text-pink-400  bg-pink-400/10  border-pink-400/20", label: "Sentiment" },
  cro:        { icon: ShieldAlert, color: "text-destructive bg-destructive/10 border-destructive/20", label: "CRO / Security" },
};

function agentMeta(name: string): { icon: typeof Bot; color: string; label: string } {
  const lower = name.toLowerCase();
  if (lower.includes("technical") || lower.includes("analysis")) return AGENT_META.technical!;
  if (lower.includes("price") || lower.includes("action"))       return AGENT_META.price!;
  if (lower.includes("risk"))                                    return AGENT_META.risk!;
  if (lower.includes("sentiment") || lower.includes("news"))     return AGENT_META.sentiment!;
  if (lower.includes("cro") || lower.includes("security"))       return AGENT_META.cro!;
  return { icon: Zap, color: "text-sky-400 bg-sky-400/10 border-sky-400/20", label: name };
}

// ── Confidence ring (visual) ─────────────────────────────────────────────────
function ConfidenceRing({ value }: { value: number | null }) {
  if (value === null) return <span className="text-muted-foreground/50">—</span>;
  const pct  = Math.round(value * 100);
  const r    = 16;
  const circ = 2 * Math.PI * r;
  const dash = (pct / 100) * circ;
  const color = pct >= 70 ? "#10b981" : pct >= 40 ? "#f59e0b" : "#ef4444";

  return (
    <div className="relative flex items-center justify-center">
      <svg width="44" height="44" viewBox="0 0 44 44" className="-rotate-90">
        <circle cx="22" cy="22" r={r} fill="none" stroke="currentColor"
          strokeWidth="3" className="text-border/40" />
        <circle cx="22" cy="22" r={r} fill="none" stroke={color}
          strokeWidth="3" strokeLinecap="round"
          strokeDasharray={`${dash} ${circ}`} />
      </svg>
      <span className="absolute text-[11px] font-bold tabular-nums text-foreground">
        {pct}%
      </span>
    </div>
  );
}

// ── Score bar ────────────────────────────────────────────────────────────────
function ScoreBar({ score }: { score: number | null }) {
  if (score === null) return <span className="text-muted-foreground/50 text-[12px]">—</span>;
  const clamped  = Math.max(-100, Math.min(100, score));
  const pct      = Math.abs(clamped) / 2; // each side is 50% of bar
  const positive = clamped >= 0;

  return (
    <div className="flex items-center gap-2">
      <div className="relative h-1.5 w-20 overflow-hidden rounded-full bg-border/40">
        <div
          className={cn(
            "absolute h-full rounded-full transition-all",
            positive ? "right-1/2 bg-success" : "left-1/2 bg-destructive",
          )}
          style={{ width: `${pct}%` }}
        />
        {/* Center line */}
        <div className="absolute left-1/2 top-0 h-full w-px bg-border/60" />
      </div>
      <span className={cn(
        "text-[12px] font-semibold tabular-nums",
        positive ? "text-success" : score < 0 ? "text-destructive" : "text-muted-foreground",
      )}>
        {score > 0 ? "+" : ""}{Math.round(score)}
      </span>
    </div>
  );
}

// ── Single agent vote card ────────────────────────────────────────────────────
function AgentVoteCard({ output }: { output: Record<string, unknown> & { agent_name?: string; id?: string } }) {
  const name      = String(output.agent_name ?? "Agent");
  const displayName = String(output.agent_display_name ?? name);
  const meta      = agentMeta(name);
  const Icon      = meta.icon;
  const payload   = (output.output as Record<string, unknown> | undefined) ?? {};
  const decision  = String(output.decision ?? payload.decision ?? "-");
  const score     = numOrNull(output.score ?? payload.score);
  const conf      = numOrNull(output.confidence ?? payload.confidence);
  const reasoning = String(output.reasoning ?? payload.reasoning ?? "");
  const veto      = Boolean(output.veto ?? payload.veto);
  const [expanded, setExpanded] = useState(false);

  return (
    <div className={cn(
      "relative overflow-hidden rounded-xl border bg-card/60 backdrop-blur-sm",
      "transition-all duration-200",
      veto ? "border-destructive/30 bg-destructive/5" : "border-border/50 hover:border-border",
    )}>
      {veto && (
        <div className="absolute inset-x-0 top-0 h-[2px] bg-destructive" />
      )}

      <div className="flex items-start gap-3 p-4">
        {/* Agent icon */}
        <div className={cn(
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border",
          meta.color,
        )}>
          <Icon className="h-4 w-4" />
        </div>

        <div className="flex-1 min-w-0">
          {/* Agent name + decision */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[13px] font-semibold text-foreground">{displayName}</span>
            <span className={cn(
              "rounded-full px-2 py-0.5 text-[11px] font-semibold",
              decision === "wait"   ? "bg-secondary text-muted-foreground"
              : decision.includes("open_long")  ? "bg-success/15 text-success"
              : decision.includes("open_short") ? "bg-destructive/15 text-destructive"
              : "bg-secondary text-foreground",
            )}>
              {decision.replace(/_/g, " ")}
            </span>
            {veto && (
              <Badge variant="destructive" className="text-[10px]">
                <ShieldAlert className="h-2.5 w-2.5" /> veto
              </Badge>
            )}
          </div>

          {/* Score + Confidence */}
          <div className="mt-2 flex items-center gap-4 flex-wrap">
            <div className="flex flex-col gap-0.5">
              <span className="text-[9px] uppercase tracking-[0.12em] text-muted-foreground/60">Score</span>
              <ScoreBar score={score} />
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-[9px] uppercase tracking-[0.12em] text-muted-foreground/60">Confidence</span>
              <ConfidenceRing value={conf} />
            </div>
          </div>
        </div>
      </div>

      {/* Reasoning (collapsible) */}
      {reasoning ? (
        <div className="border-t border-border/20">
          <button
            onClick={() => setExpanded((p) => !p)}
            className="flex w-full items-center justify-between px-4 py-2 text-[11px] text-muted-foreground/60 hover:text-foreground transition-colors"
          >
            <span>Reasoning</span>
            <ChevronRight className={cn("h-3.5 w-3.5 transition-transform", expanded && "rotate-90")} />
          </button>
          {expanded && (
            <div className="px-4 pb-4">
              <p className="text-[12px] leading-relaxed text-muted-foreground whitespace-pre-wrap">
                {reasoning}
              </p>
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────
export default function DecisionDetailPage() {
  const params     = useParams<{ decisionId: string }>();
  const decisionId = params.decisionId;
  const decisionQ  = useDecision(decisionId);
  const decision   = decisionQ.data ?? null;
  const signalQ    = useSignal(decision?.signal_id ?? null);
  const runsQ      = useDecisionAgentRuns(decisionId, decision?.agent_run_id ?? null);
  const primaryRun = runsQ.data?.[0] ?? null;
  const outputsQ   = useAgentOutputs(primaryRun?.id ?? null);
  const tradeQ     = useTradeForDecision(decisionId);
  const eventsQ    = useTradeEventsForDecision(decisionId);

  useEffect(() => {
    if (decisionQ.isError)
      console.error("decision.detail.load.failed", { decision_id: decisionId, error: decisionQ.error });
  }, [decisionId, decisionQ.error, decisionQ.isError]);

  if (decisionQ.isLoading) {
    return (
      <ProductPage size="lg">
        <Skeleton className="h-9 w-72 rounded-xl" />
        <Skeleton className="h-40 w-full rounded-2xl" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[...Array(5)].map((_, i) => <Skeleton key={i} className="h-44 rounded-xl" />)}
        </div>
      </ProductPage>
    );
  }

  if (decisionQ.isError) {
    return (
      <ProductPage size="md">
        <ErrorState
          title="Could not load decision"
          message={String((decisionQ.error as Error)?.message ?? "")}
          onRetry={() => void decisionQ.refetch()}
        />
      </ProductPage>
    );
  }

  if (!decision) {
    return (
      <ProductPage size="md">
        <EmptyState
          title="Decision not found"
          description={`No record for id ${decisionId}`}
        />
      </ProductPage>
    );
  }

  const score      = getDecisionScore(decision);
  const confidenceRaw = getDecisionConfidence(decision);
  const confidence = num(confidenceRaw);
  const rationale  = getDecisionRationale(decision) ?? getDecisionReasoning(decision);

  const isWarmingUp = decision.metadata?.warming_up === true;
  const isReject    = decision.final_decision === "reject" ||
                      decision.approval_status === "rejected" ||
                      decision.execution_status === "skipped";
  const isExecuted  = decision.execution_status === "executed" || !!decision.linked_trade_id;

  const warmupHave = num(decision.metadata?.candles_available);
  const warmupNeed = num(decision.metadata?.candles_required);

  const outcomeColor = isWarmingUp ? "border-warning/20  bg-warning/5"
    : isReject ? "border-destructive/20 bg-destructive/5"
    : isExecuted ? "border-success/20  bg-success/5"
    : "border-border/50 bg-card/60";

  const OutcomeIcon = isWarmingUp ? Clock : isReject ? ShieldAlert : ShieldCheck;
  const outcomeIconColor = isWarmingUp ? "text-warning" : isReject ? "text-destructive" : "text-success";

  return (
    <ProductPage size="lg">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <PageHeader
        eyebrow="Decision detail"
        title={`${decision.symbol} · ${decision.final_decision.replace(/_/g, " ")}`}
        description={`Decision recorded ${formatDateTime(decision.created_at)}`}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {isWarmingUp ? <Badge variant="warning"><Clock className="h-3 w-3" /> warming up</Badge> : null}
            {isExecuted  ? <Badge variant="success">executed</Badge> : null}
            {isReject    ? <Badge variant="destructive">rejected</Badge> : null}
            <Badge variant="secondary">{decision.mode}</Badge>
            <Link href="/decisions">
              <Button size="sm" variant="outline" className="gap-1.5">
                <ArrowLeft className="h-3.5 w-3.5" /> All decisions
              </Button>
            </Link>
          </div>
        }
      />

      {/* ── Outcome hero card ───────────────────────────────────────────────── */}
      <div className={cn(
        "relative overflow-hidden rounded-2xl border p-6 backdrop-blur-sm",
        outcomeColor,
      )}>
        <div className="flex items-start gap-4">
          <div className={cn(
            "flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border",
            isWarmingUp ? "border-warning/20 bg-warning/10"
            : isReject  ? "border-destructive/20 bg-destructive/10"
            : "border-success/20 bg-success/10",
          )}>
            <OutcomeIcon className={cn("h-6 w-6", outcomeIconColor)} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[15px] font-bold text-foreground">
              {isWarmingUp ? "Bot is warming up"
               : isReject ? "Signal rejected"
               : isExecuted ? `Opened ${decision.final_decision.replace(/_/g, " ")}`
               : `Decision: ${decision.final_decision.replace(/_/g, " ")}`}
            </div>
            {isWarmingUp && warmupHave != null && warmupNeed != null ? (
              <div className="mt-2 space-y-2">
                <p className="text-[13px] text-muted-foreground">
                  Needs {warmupNeed} candles, {warmupHave} collected so far. Resumes automatically.
                </p>
                <div className="flex items-center gap-3">
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-border/40">
                    <div
                      className="h-full rounded-full bg-warning transition-all"
                      style={{ width: `${Math.min(100, (warmupHave / warmupNeed) * 100).toFixed(1)}%` }}
                    />
                  </div>
                  <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">
                    {warmupHave}/{warmupNeed}
                  </span>
                </div>
              </div>
            ) : rationale ? (
              <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">{rationale}</p>
            ) : null}
          </div>
          {/* Score + Confidence on the right */}
          <div className="flex shrink-0 flex-col items-end gap-3">
            <div className="text-right">
              <div className="text-[9px] uppercase tracking-[0.12em] text-muted-foreground/60">Score</div>
              <div className={cn(
                "text-xl font-bold tabular-nums",
                (score ?? 0) > 0 ? "text-success" : (score ?? 0) < 0 ? "text-destructive" : "text-foreground",
              )}>
                {score != null ? (score > 0 ? "+" : "") + Math.round(score) : "—"}
              </div>
            </div>
            {confidence != null && <ConfidenceRing value={confidence} />}
          </div>
        </div>

        {/* Meta fields */}
        <div className="mt-4 grid grid-cols-2 gap-3 border-t border-border/20 pt-4 text-[12px] sm:grid-cols-4">
          <MetaField label="Direction"   value={decision.direction} />
          <MetaField label="Symbol"      value={<span className="font-mono">{decision.symbol}</span>} />
          <MetaField label="Approval"    value={decision.approval_status.replace(/_/g, " ")} />
          <MetaField label="Execution"   value={decision.execution_status.replace(/_/g, " ")} />
          {decision.linked_trade_id ? (
            <div className="col-span-2 sm:col-span-4">
              <span className="text-[9px] uppercase tracking-[0.12em] text-muted-foreground/60">Linked trade</span>
              <Link
                href={`/trades/${decision.linked_trade_id}`}
                className="ml-2 font-mono text-primary underline-offset-4 hover:underline"
              >
                {decision.linked_trade_id.slice(0, 12)}…
              </Link>
            </div>
          ) : null}
        </div>
      </div>

      {/* ── Agent voting panel ──────────────────────────────────────────────── */}
      <DecisionExecutionPanel
        decision={decision}
        decisionStatus={decision.execution_status}
        approvalStatus={decision.approval_status}
        trade={tradeQ.data ?? null}
        isLoading={tradeQ.isLoading}
      />
      <DecisionTakeProfitPlanCard decision={decision} trade={tradeQ.data ?? null} />

      <div>
        <div className="mb-3 flex items-center gap-2">
          <h2 className="text-[15px] font-semibold text-foreground">Agent votes</h2>
          <span className="text-[12px] text-muted-foreground">
            {runsQ.isLoading ? "…" : `${(outputsQ.data ?? []).length} agents`}
          </span>
        </div>

        {runsQ.isLoading ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-40 rounded-xl" />)}
          </div>
        ) : !primaryRun ? (
          <EmptyState title="No agent run found" description="No pipeline data recorded for this decision." />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {(outputsQ.data ?? []).map((o) => (
              <AgentVoteCard key={o.id} output={{ ...o, agent_name: o.agent_name ?? undefined }} />
            ))}
          </div>
        )}
      </div>

      {/* ── Risk / Security / Veto summaries ───────────────────────────────── */}
      <div className="grid gap-4 lg:grid-cols-3">
        <SummaryCard title="Risk checks"     summary={decision.risk_summary as Record<string, unknown> | null} />
        <SummaryCard title="Security checks" summary={decision.security_summary as Record<string, unknown> | null} />
        <SummaryCard title="Veto"            summary={decision.veto_summary as Record<string, unknown> | null} />
      </div>

      {/* ── Signal + Trade ──────────────────────────────────────────────────── */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Source signal</CardTitle>
            <CardDescription>The signal that triggered this pipeline run.</CardDescription>
          </CardHeader>
          <CardContent>
            {signalQ.isLoading ? <Skeleton className="h-24 w-full rounded-lg" />
            : !signalQ.data ? <EmptyState title="No signal recorded" />
            : (
              <div className="grid gap-2 text-[13px] sm:grid-cols-2">
                {(() => {
                  const sig = signalQ.data as unknown as Record<string, unknown>;
                  return (
                    <>
                      <MetaField label="Symbol"    value={<span className="font-mono">{signalQ.data.symbol}</span>} />
                      <MetaField label="Direction" value={sig.direction != null ? String(sig.direction) : "—"} />
                      <MetaField label="Type"      value={signalQ.data.signal_type} />
                      <MetaField label="Status"    value={sig.status != null ? String(sig.status) : "—"} />
                      <MetaField label="Created"   value={formatRelative(signalQ.data.created_at)} />
                    </>
                  );
                })()}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Resulting trade</CardTitle>
            <CardDescription>If the decision opened a position.</CardDescription>
          </CardHeader>
          <CardContent>
            {tradeQ.isLoading ? <Skeleton className="h-24 w-full rounded-lg" />
            : !tradeQ.data ? (
              <EmptyState
                title="No trade opened"
                description={isReject ? "Decision rejected — no trade created." : "No trade linked yet."}
              />
            ) : (
              <div className="space-y-3 text-[13px]">
                <Link
                  href={`/trades/${tradeQ.data.id}`}
                  className="flex items-center justify-between rounded-lg border border-border/50 bg-card/60 px-3 py-2 hover:border-primary/30 transition-colors"
                >
                  <span className="font-mono text-[12px] text-muted-foreground">
                    {tradeQ.data.id.slice(0, 16)}…
                  </span>
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                </Link>
                <div className="grid gap-2 sm:grid-cols-2">
                  <MetaField label="Status"      value={tradeQ.data.status} />
                  <MetaField label="Entry price" value={formatPrice(tradeQ.data.entry_price)} />
                  <MetaField label="P&L"         value={
                    tradeQ.data.realized_pnl != null ? formatCurrency(tradeQ.data.realized_pnl)
                    : tradeQ.data.unrealized_pnl != null ? `${formatCurrency(tradeQ.data.unrealized_pnl)} (open)` : "—"
                  } />
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── Lifecycle events ────────────────────────────────────────────────── */}
      {(eventsQ.data ?? []).length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Lifecycle events</CardTitle>
            <CardDescription>Events tied to this decision in chronological order.</CardDescription>
          </CardHeader>
          <CardContent>
            <ol className="space-y-2">
              {eventsQ.data!.map((e) => (
                <li key={e.id} className="flex items-start justify-between gap-3 rounded-xl border border-border/40 bg-card/40 px-4 py-3 text-[13px]">
                  <div>
                    <div className="font-medium">{e.event_type}</div>
                    {Object.keys(e.metadata ?? {}).length > 0 ? (
                      <p className="mt-0.5 line-clamp-1 font-mono text-[11px] text-muted-foreground">
                        {JSON.stringify(e.metadata)}
                      </p>
                    ) : null}
                  </div>
                  <span className="shrink-0 text-[11px] text-muted-foreground">
                    {formatRelative(e.created_at)}
                  </span>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      ) : null}

      {/* ── Raw JSON (collapsible) ───────────────────────────────────────────── */}
      <CollapsibleJson title="Raw decision row" data={decision} />
      {primaryRun ? <CollapsibleJson title="Raw agent run" data={primaryRun} /> : null}
    </ProductPage>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function DecisionExecutionPanel({
  decision,
  decisionStatus,
  approvalStatus,
  trade,
  isLoading,
}: {
  decision: TradeDecision;
  decisionStatus: string;
  approvalStatus: string;
  trade: Trade | null;
  isLoading: boolean;
}) {
  if (isLoading) return <Skeleton className="h-24 rounded-xl" />;

  const explanation = explainDecisionExecution(decision, trade);
  const isOpened = trade?.status === "open";
  const isClosed = trade?.status === "closed";
  const pnl = trade
    ? isOpened
      ? Number(trade.unrealized_pnl ?? trade.pnl ?? 0)
      : Number(trade.realized_pnl ?? trade.pnl ?? 0)
    : null;
  const pnlPct = trade?.pnl_pct != null ? Number(trade.pnl_pct) : null;

  return (
    <div className="space-y-3">
      <div className={cn(
        "rounded-xl border px-4 py-3 text-[13px] leading-relaxed",
        explanation.tone === "success" ? "border-success/25 bg-success/5 text-success"
        : explanation.tone === "destructive" ? "border-destructive/25 bg-destructive/5 text-destructive"
        : explanation.tone === "warning" ? "border-warning/25 bg-warning/5 text-warning"
        : "border-border/40 bg-card/50 text-muted-foreground",
      )}>
        <div className="text-[9px] font-semibold uppercase tracking-[0.12em] opacity-70">Execution explanation</div>
        <div className="mt-1 text-foreground">{explanation.title}</div>
        <div className="mt-0.5">{explanation.detail}</div>
      </div>
      <div className="grid gap-3 md:grid-cols-4">
        <DecisionStateTile
          label="Decision"
          value={decisionStatus.replace(/_/g, " ")}
          detail={`Approval: ${approvalStatus.replace(/_/g, " ")}`}
          tone={decisionStatus === "executed" ? "success" : decisionStatus === "failed" ? "destructive" : decisionStatus === "skipped" ? "muted" : "warning"}
        />
        <DecisionStateTile
          label="Trade"
          value={trade ? trade.status.replace(/_/g, " ") : "No trade"}
          detail={trade ? trade.lifecycle_status.replace(/_/g, " ") : "Nothing opened yet"}
          tone={isClosed ? "muted" : isOpened ? "success" : trade ? "warning" : "muted"}
        />
        <DecisionStateTile
          label="Entry"
          value={trade ? formatPrice(Number(trade.avg_fill_price ?? trade.avg_entry_price ?? trade.entry_price)) : "-"}
          detail={trade?.filled_quantity != null ? `Filled ${Number(trade.filled_quantity).toFixed(8)}` : "Fill pending"}
        />
        <DecisionStateTile
          label="P&L"
          value={pnl != null ? `${pnl >= 0 ? "+" : ""}${formatCurrency(pnl)}` : "-"}
          detail={pnlPct != null ? `${pnlPct >= 0 ? "+" : ""}${pnlPct.toFixed(2)}%` : "No P&L yet"}
          className={pnl != null && pnl > 0 ? "text-success" : pnl != null && pnl < 0 ? "text-destructive" : undefined}
        />
      </div>
    </div>
  );
}

function DecisionStateTile({
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
      <div className={cn("mt-1 text-[14px] font-semibold capitalize text-foreground", className)}>{value}</div>
      <div className="mt-0.5 text-[11px] text-muted-foreground">{detail}</div>
    </div>
  );
}

function DecisionTakeProfitPlanCard({
  decision,
  trade,
}: {
  decision: TradeDecision;
  trade: Trade | null;
}) {
  const plan = getDecisionRewardPlan(decision, trade);
  const levels = getDecisionTpLevels(plan, decision, trade);
  if (levels.length === 0) return null;

  const selectedR = num(plan?.selected_reward_r ?? decision.risk_summary?.risk_reward_ratio ?? trade?.risk_reward_ratio);
  const realized = num(trade?.realized_pnl) ?? 0;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Target className="h-4 w-4 text-muted-foreground/50" />
          <CardTitle>Take-profit plan</CardTitle>
        </div>
        <CardDescription>AI-selected scaled TP levels for this decision.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-3">
          {levels.map((level) => {
            const status = String(level.status ?? "pending");
            const closePct = normalizePct(num(level.close_pct));
            const levelPnl = num(level.realized_pnl);
            return (
              <div
                key={`${String(level.label ?? "TP")}-${String(level.level ?? "")}`}
                className={cn(
                  "rounded-xl border px-4 py-3",
                  status === "hit" ? "border-success/25 bg-success/5" : "border-border/40 bg-card/50",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="text-[13px] font-semibold text-foreground">
                    {String(level.label ?? `TP${String(level.level ?? "")}`)}
                  </div>
                  <Badge variant={status === "hit" ? "success" : "secondary"} className="text-[10px]">
                    {status.replace(/_/g, " ")}
                  </Badge>
                </div>
                <div className="mt-2 space-y-1">
                  <PlanMetric label="Price" value={num(level.price) != null ? formatPrice(Number(level.price)) : "-"} />
                  <PlanMetric label="R" value={num(level.r) != null ? `${Number(level.r).toFixed(2)}R` : "-"} />
                  <PlanMetric label="Close" value={closePct != null ? `${closePct.toFixed(0)}%` : "-"} />
                  {levelPnl != null ? (
                    <PlanMetric
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
        <div className="grid gap-3 md:grid-cols-3">
          <DecisionStateTile
            label="Selected R"
            value={selectedR != null ? `${selectedR.toFixed(2)}R` : "-"}
            detail="Chosen by Reward Plan Agent"
          />
          <DecisionStateTile
            label="Final TP"
            value={num(levels.at(-1)?.price) != null ? formatPrice(Number(levels.at(-1)?.price)) : "-"}
            detail="Last remaining quantity"
          />
          <DecisionStateTile
            label="Realized"
            value={`${realized >= 0 ? "+" : ""}${formatCurrency(realized)}`}
            detail={trade ? "Updated after partial TP fills" : "No trade linked yet"}
            tone={realized > 0 ? "success" : realized < 0 ? "destructive" : "muted"}
          />
        </div>
      </CardContent>
    </Card>
  );
}

function PlanMetric({
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

function getDecisionRewardPlan(decision: TradeDecision, trade: Trade | null): Record<string, unknown> | null {
  const tradePlan = trade?.metadata?.reward_plan;
  if (isRecord(tradePlan)) return tradePlan;
  const decisionPlan = decision.risk_summary?.reward_plan;
  return isRecord(decisionPlan) ? decisionPlan : null;
}

function getDecisionTpLevels(
  plan: Record<string, unknown> | null,
  decision: TradeDecision,
  trade: Trade | null,
): Record<string, unknown>[] {
  const planLevels = plan?.levels;
  if (Array.isArray(planLevels)) return planLevels.filter(isRecord);
  const tradeLevels = trade?.metadata?.tp_plan;
  if (Array.isArray(tradeLevels)) return tradeLevels.filter(isRecord);
  const decisionLevels = decision.risk_summary?.tp_plan;
  return Array.isArray(decisionLevels) ? decisionLevels.filter(isRecord) : [];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function normalizePct(value: number | null): number | null {
  if (value == null) return null;
  return value <= 1 ? value * 100 : value;
}

function num(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") { const n = Number(value); if (Number.isFinite(n)) return n; }
  return null;
}

function numOrNull(value: unknown): number | null { return num(value); }

function explainDecisionExecution(decision: TradeDecision, trade: Trade | null): {
  title: string;
  detail: string;
  tone: "success" | "warning" | "destructive" | "muted";
} {
  const finalDecision = decision.final_decision.replace(/_/g, " ");
  const approval = decision.approval_status.replace(/_/g, " ");
  const execution = decision.execution_status.replace(/_/g, " ");
  const error = typeof decision.execution_error === "string" && decision.execution_error.trim()
    ? decision.execution_error.trim()
    : null;

  if (trade) {
    return {
      title: "This decision opened a trade.",
      detail: `Execution status is ${execution}; linked trade status is ${trade.status.replace(/_/g, " ")}.`,
      tone: trade.status === "closed" ? "muted" : "success",
    };
  }

  if (!["open_long", "open_short"].includes(decision.final_decision)) {
    return {
      title: "No trade was opened by design.",
      detail: `Only open long/open short decisions are executable. This row ended as ${finalDecision}, so score alone is not enough to create a position.`,
      tone: decision.final_decision === "reject" || decision.final_decision === "pause_trading" ? "destructive" : "muted",
    };
  }

  if (!["approved", "auto_approved"].includes(decision.approval_status)) {
    return {
      title: "Execution is waiting for approval.",
      detail: `The decision is ${finalDecision}, but approval is ${approval}. The execution engine only claims approved or auto approved rows.`,
      tone: "warning",
    };
  }

  if (decision.execution_status === "pending_execution") {
    return {
      title: "Approved, but not claimed by the execution engine yet.",
      detail: "If this stays here, check whether the execution-engine worker is running and whether the decision is still unlinked.",
      tone: "warning",
    };
  }

  if (decision.execution_status === "executing") {
    return {
      title: "Execution is currently in progress.",
      detail: "The worker has claimed this decision. If it remains in this state too long, the stuck-execution recovery should release or fail it.",
      tone: "warning",
    };
  }

  if (decision.execution_status === "skipped") {
    return {
      title: "Execution was intentionally skipped.",
      detail: error ?? "A guard blocked execution, usually to enforce live gate, risk, security, or exposure rules.",
      tone: "muted",
    };
  }

  if (decision.execution_status === "failed") {
    return {
      title: "Execution failed before opening a trade.",
      detail: error ?? "No execution error was recorded; inspect raw decision data and service logs.",
      tone: "destructive",
    };
  }

  return {
    title: "No linked trade found.",
    detail: `Decision is ${finalDecision}, approval is ${approval}, execution is ${execution}.`,
    tone: "muted",
  };
}

function MetaField({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-[9px] font-semibold uppercase tracking-[0.12em] text-muted-foreground/60">{label}</div>
      <div className="mt-0.5 text-[13px] text-foreground">{value}</div>
    </div>
  );
}

function SummaryCard({ title, summary }: { title: string; summary: Record<string, unknown> | null | undefined }) {
  const entries = useMemo(() => {
    if (!summary) return [];
    return Object.entries(summary).filter(
      ([, v]) => typeof v === "string" || typeof v === "number" || typeof v === "boolean"
    );
  }, [summary]);

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-[13px]">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {!summary || entries.length === 0 ? (
          <div className="text-[12px] text-muted-foreground/50">No data recorded</div>
        ) : (
          <ul className="space-y-1.5">
            {entries.map(([k, v]) => (
              <li key={k} className="flex items-baseline justify-between gap-2">
                <span className="text-[10px] uppercase tracking-wider text-muted-foreground/60">
                  {k.replace(/_/g, " ")}
                </span>
                <span className={cn(
                  "text-right font-mono text-[11px]",
                  v === true ? "text-success" : v === false ? "text-destructive" : "text-foreground",
                )}>
                  {String(v)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function CollapsibleJson({ title, data }: { title: string; data: unknown }) {
  const [open, setOpen] = useState(false);
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 py-3">
        <CardTitle className="text-[13px] text-muted-foreground">{title}</CardTitle>
        <Button size="sm" variant="ghost" className="h-7 text-[11px]" onClick={() => setOpen((o) => !o)}>
          {open ? "Hide" : "Show"} raw
        </Button>
      </CardHeader>
      {open ? (
        <CardContent>
          <pre className="max-h-96 overflow-auto rounded-xl bg-muted/30 p-4 text-[11px] leading-relaxed text-muted-foreground">
            {JSON.stringify(data, null, 2)}
          </pre>
        </CardContent>
      ) : null}
    </Card>
  );
}
