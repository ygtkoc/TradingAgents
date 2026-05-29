"use client";

import {
  Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle,
  EmptyState, ErrorState, PageHeader, ProductPage, Skeleton,
} from "@ta/ui";
import { cn, formatCurrency, formatDateTime, formatRelative } from "@ta/utils";
import { ArrowDownRight, ArrowLeft, ArrowUpRight, ReceiptText } from "lucide-react";
import { useParams, useRouter } from "next/navigation";

import { formatPrice } from "@/lib/format-price";
import type { PaperAccountEvent } from "@/lib/hooks/queries/use-paper-account";
import { usePaperAccountEvents } from "@/lib/hooks/queries/use-paper-account";

type LedgerType = "income" | "expense" | "ledger";

const PAGE_META: Record<LedgerType, { title: string; description: string }> = {
  income: {
    title: "Total income details",
    description: "All positive paper-account ledger movements and the trades or events that created them.",
  },
  expense: {
    title: "Total expense details",
    description: "All negative paper-account ledger movements and the trades or events that consumed balance.",
  },
  ledger: {
    title: "Net ledger details",
    description: "Every paper-account balance movement, with source, destination, and running balance.",
  },
};

export default function PaperLedgerDetailPage() {
  const router = useRouter();
  const params = useParams<{ ledgerType: string }>();
  const ledgerType = normalizeLedgerType(params.ledgerType);
  const meta = PAGE_META[ledgerType];
  const events = usePaperAccountEvents(500, true);

  const rows = (events.data ?? [])
    .map((event) => ({ event, movement: ledgerMovement(event) }))
    .filter(({ movement }) => {
      if (ledgerType === "income") return movement.visibleDelta > 0;
      if (ledgerType === "expense") return movement.visibleDelta < 0;
      return movement.visibleDelta !== 0 || movement.cashDelta !== 0 || movement.realizedDelta !== 0;
    });
  const total = rows.reduce((sum, row) => sum + row.movement.visibleDelta, 0);

  return (
    <ProductPage size="xl">
      <PageHeader
        eyebrow="Paper ledger"
        title={meta.title}
        description={meta.description}
        actions={
          <Button type="button" variant="outline" onClick={() => router.push("/paper")}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to paper
          </Button>
        }
      />

      <div className="grid gap-3 sm:grid-cols-3">
        <SummaryTile label="Filtered movement" value={formatSignedCurrency(total)} tone={toneFor(total)} />
        <SummaryTile label="Ledger rows" value={String(rows.length)} tone="neutral" />
        <SummaryTile
          label="Last update"
          value={rows[0]?.event.created_at ? formatRelative(rows[0].event.created_at) : "-"}
          tone="neutral"
        />
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <ReceiptText className="h-4 w-4 text-muted-foreground/55" />
            <CardTitle>Movements</CardTitle>
          </div>
          <CardDescription>Each row explains where the value came from and how the balance changed.</CardDescription>
        </CardHeader>
        <CardContent>
          {events.isError ? (
            <ErrorState title="Ledger unavailable" onRetry={() => void events.refetch()} />
          ) : events.isLoading ? (
            <Skeleton className="h-48 w-full rounded-xl" />
          ) : rows.length === 0 ? (
            <EmptyState title="No matching ledger movement" />
          ) : (
            <ol className="space-y-2">
              {rows.map(({ event, movement }) => (
                <LedgerRow key={event.id} event={event} movement={movement} />
              ))}
            </ol>
          )}
        </CardContent>
      </Card>
    </ProductPage>
  );
}

function normalizeLedgerType(value: string | undefined): LedgerType {
  return value === "income" || value === "expense" || value === "ledger" ? value : "ledger";
}

function SummaryTile({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "income" | "expense" | "neutral";
}) {
  return (
    <div className="rounded-xl border border-border/40 bg-card/55 px-4 py-3">
      <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground/60">{label}</div>
      <div className={cn(
        "mt-1 text-xl font-bold tabular-nums",
        tone === "income" ? "text-success" : tone === "expense" ? "text-destructive" : "text-foreground",
      )}>
        {value}
      </div>
    </div>
  );
}

interface Movement {
  cashDelta: number;
  realizedDelta: number;
  unrealizedDelta: number;
  visibleDelta: number;
  balanceAfter: number;
  balanceBefore: number;
}

function LedgerRow({ event, movement }: { event: PaperAccountEvent; movement: Movement }) {
  const trade = event.trades;
  const symbol = trade?.symbol ?? String(event.metadata?.symbol ?? "");
  const source = symbol || event.event_type.replace(/_/g, " ");
  const isIncome = movement.visibleDelta > 0;

  return (
    <li className="rounded-xl border border-border/35 bg-card/45 px-4 py-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold text-foreground">{source}</span>
            <Badge variant={isIncome ? "success" : movement.visibleDelta < 0 ? "destructive" : "outline"} className="text-[10px]">
              {event.event_type.replace(/_/g, " ")}
            </Badge>
            {trade?.direction ? (
              <Badge variant="secondary" className="text-[10px]">{trade.direction}</Badge>
            ) : null}
            <span className="text-[11px] text-muted-foreground/65">{formatDateTime(event.created_at)}</span>
          </div>
          <div className="mt-1 text-[12px] text-muted-foreground">
            {explainEvent(event, movement)}
          </div>
          {event.note ? (
            <div className="mt-1 text-[12px] text-muted-foreground">{event.note}</div>
          ) : null}
        </div>

        <div className={cn(
          "flex items-center gap-1 text-right text-[15px] font-bold tabular-nums",
          isIncome ? "text-success" : movement.visibleDelta < 0 ? "text-destructive" : "text-foreground",
        )}>
          {isIncome ? <ArrowUpRight className="h-4 w-4" /> : movement.visibleDelta < 0 ? <ArrowDownRight className="h-4 w-4" /> : null}
          {formatSignedCurrency(movement.visibleDelta)}
        </div>
      </div>

      <div className="mt-3 grid gap-2 text-[12px] sm:grid-cols-2 lg:grid-cols-5">
        <DetailCell label="Cash delta" value={formatSignedCurrency(movement.cashDelta)} tone={toneFor(movement.cashDelta)} />
        <DetailCell label="Realized delta" value={formatSignedCurrency(movement.realizedDelta)} tone={toneFor(movement.realizedDelta)} />
        <DetailCell label="Unrealized delta" value={formatSignedCurrency(movement.unrealizedDelta)} tone={toneFor(movement.unrealizedDelta)} />
        <DetailCell label="Before" value={formatCurrency(movement.balanceBefore)} tone="neutral" />
        <DetailCell label="After" value={formatCurrency(movement.balanceAfter)} tone="neutral" />
      </div>

      {trade ? (
        <div className="mt-2 grid gap-2 text-[12px] sm:grid-cols-2 lg:grid-cols-4">
          <DetailCell label="Entry" value={trade.entry_price ? formatPrice(trade.entry_price) : "-"} tone="neutral" />
          <DetailCell label="Exit" value={trade.exit_price ? formatPrice(trade.exit_price) : "-"} tone="neutral" />
          <DetailCell label="Trade P&L" value={trade.realized_pnl != null ? formatSignedCurrency(Number(trade.realized_pnl)) : "-"} tone={toneFor(Number(trade.realized_pnl ?? 0))} />
          <DetailCell label="Close reason" value={trade.close_reason?.replace(/_/g, " ") ?? "-"} tone="neutral" />
        </div>
      ) : null}

      {event.metadata && Object.keys(event.metadata).length > 0 ? (
        <details className="mt-2">
          <summary className="cursor-pointer text-[11px] text-muted-foreground hover:text-foreground">
            Metadata
          </summary>
          <pre className="mt-1 max-h-44 overflow-auto rounded-lg bg-muted/35 p-2 text-[11px]">
            {JSON.stringify(event.metadata, null, 2)}
          </pre>
        </details>
      ) : null}
    </li>
  );
}

function DetailCell({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "income" | "expense" | "neutral";
}) {
  return (
    <div className="rounded-lg border border-border/30 bg-background/25 px-3 py-2">
      <div className="text-[9px] font-semibold uppercase tracking-[0.12em] text-muted-foreground/55">{label}</div>
      <div className={cn(
        "mt-0.5 font-medium tabular-nums",
        tone === "income" ? "text-success" : tone === "expense" ? "text-destructive" : "text-foreground",
      )}>
        {value}
      </div>
    </div>
  );
}

function ledgerMovement(event: PaperAccountEvent): Movement {
  const cashDelta = safeNum(event.delta);
  const realizedDelta = safeNum(event.realized_delta);
  const unrealizedDelta = safeNum(event.unrealized_delta);
  const eventType = String(event.event_type ?? "");
  const preferRealized = realizedDelta !== 0 || eventType.includes("close") || eventType.includes("settle");
  const visibleDelta = preferRealized ? realizedDelta : cashDelta;
  const balanceAfter = safeNum(event.balance_after);
  return {
    cashDelta,
    realizedDelta,
    unrealizedDelta,
    visibleDelta,
    balanceAfter,
    balanceBefore: balanceAfter - cashDelta,
  };
}

function explainEvent(event: PaperAccountEvent, movement: Movement): string {
  const trade = event.trades;
  const symbol = trade?.symbol ?? String(event.metadata?.symbol ?? "");
  const base = event.event_type.replace(/_/g, " ");
  if (trade && movement.visibleDelta !== 0) {
    const direction = trade.direction ? ` ${trade.direction}` : "";
    return `${base} from${direction} ${symbol || "trade"}; value moved into the paper account ledger.`;
  }
  if (movement.cashDelta !== 0) {
    return `${base}; cash balance changed by ${formatSignedCurrency(movement.cashDelta)}.`;
  }
  return `${base}; no cash movement, but the event is kept for audit detail.`;
}

function formatSignedCurrency(value: number): string {
  return `${value >= 0 ? "+" : ""}${formatCurrency(value)}`;
}

function toneFor(value: number): "income" | "expense" | "neutral" {
  return value > 0 ? "income" : value < 0 ? "expense" : "neutral";
}

function safeNum(value: unknown): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}
