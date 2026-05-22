"use client";

import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle, EmptyState, ErrorState, Skeleton } from "@ta/ui";
import { cn, formatCurrency, formatDateTime } from "@ta/utils";

import { formatPrice } from "@/lib/format-price";
import { useTradeEvents } from "@/lib/hooks/queries/use-trade-events";

interface Props {
  tradeId: string;
}

export function TradeTimeline({ tradeId }: Props) {
  const { data, isLoading, isError, refetch } = useTradeEvents(tradeId);

  if (isError) {
    return <ErrorState onRetry={() => void refetch()} />;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Trade timeline</CardTitle>
        <CardDescription>Position lifecycle in the order it happened.</CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : !data || data.length === 0 ? (
          <EmptyState title="No events yet" description="Lifecycle events will appear here as the trade is monitored." />
        ) : (
          <ol className="relative space-y-4 border-l border-border pl-4">
            {data.map((e) => (
              <li key={e.id} className="relative">
                <span className={cn("absolute -left-[1.4rem] top-1 inline-block h-2 w-2 rounded-full", eventDot(e.event_type))} />
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <div className="text-sm font-medium">{eventTitle(e.event_type)}</div>
                    <Badge variant={eventVariant(e.event_type)} className="text-[10px]">
                      {e.event_type.replace(/_/g, " ")}
                    </Badge>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {formatDateTime(e.created_at)}
                  </div>
                </div>
                <EventExplanation eventType={e.event_type} details={eventDetails(e)} />
                <EventDetails details={eventDetails(e)} />
                {Object.keys(eventDetails(e)).length > 0 ? (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-[11px] text-muted-foreground hover:text-foreground">
                      Raw event data
                    </summary>
                    <pre className="mt-1 overflow-auto rounded bg-muted/40 p-2 text-[11px]">
                      {JSON.stringify(eventDetails(e), null, 2)}
                    </pre>
                  </details>
                ) : null}
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}

function eventTitle(type: string): string {
  if (type.includes("opened") || type.includes("filled")) return "Position opened";
  if (type.includes("pnl")) return "P&L updated";
  if (type.includes("price")) return "Price checked";
  if (type.includes("stop_loss")) return "Stop-loss triggered";
  if (type.includes("take_profit")) return "Take-profit triggered";
  if (type.includes("trailing")) return "Trailing stop updated";
  if (type.includes("closed")) return "Position closed";
  if (type.includes("failed") || type.includes("error")) return "Action failed";
  return type.replace(/_/g, " ");
}

function eventVariant(type: string): "default" | "secondary" | "success" | "warning" | "destructive" | "outline" {
  if (type.includes("failed") || type.includes("error") || type.includes("stop_loss")) return "destructive";
  if (type.includes("take_profit") || type.includes("opened") || type.includes("closed")) return "success";
  if (type.includes("trailing") || type.includes("price")) return "secondary";
  return "outline";
}

function eventDot(type: string): string {
  if (type.includes("failed") || type.includes("error") || type.includes("stop_loss")) return "bg-destructive";
  if (type.includes("take_profit") || type.includes("opened") || type.includes("closed")) return "bg-success";
  return "bg-primary";
}

function EventExplanation({ eventType, details }: { eventType: string; details: Record<string, unknown> }) {
  const explanation = explainEvent(eventType, details);
  if (!explanation) return null;

  return (
    <div className={cn(
      "mt-2 rounded-lg border px-3 py-2 text-[12px] leading-relaxed",
      eventType.includes("stop_loss") || eventType.includes("emergency")
        ? "border-destructive/25 bg-destructive/5 text-destructive"
        : eventType.includes("take_profit")
          ? "border-success/25 bg-success/5 text-success"
          : "border-border/40 bg-card/40 text-muted-foreground",
    )}>
      {explanation}
    </div>
  );
}

function EventDetails({ details }: { details: Record<string, unknown> }) {
  const fields = [
    pickPrice(details, "fill_price", "Fill"),
    pickPrice(details, "entry_price", "Entry"),
    pickPrice(details, "current_price", "Price"),
    pickPrice(details, "close_price", "Close"),
    pickPrice(details, "stop_loss", "Stop loss"),
    pickPrice(details, "take_profit", "Take profit"),
    pickNumber(details, "stop_distance_pct", "Stop distance", "%"),
    pickNumber(details, "price_move_pct", "Move from entry", "%"),
    pickMoney(details, "realized_pnl", "Realized"),
    pickMoney(details, "unrealized_pnl", "Unrealized"),
    pickNumber(details, "pnl_pct", "P&L %", "%"),
    pickNumber(details, "filled_qty", "Filled"),
    pickNumber(details, "quantity", "Qty"),
    pickMoney(details, "risk_amount", "Risk"),
  ].filter(Boolean) as Array<{ label: string; value: string }>;

  if (fields.length === 0) return null;

  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {fields.map((field) => (
        <span key={field.label} className="rounded-md border border-border/40 bg-card/50 px-2 py-1 text-[11px]">
          <span className="text-muted-foreground">{field.label}</span>{" "}
          <span className="font-mono text-foreground">{field.value}</span>
        </span>
      ))}
    </div>
  );
}

function eventDetails(event: { details?: Record<string, unknown> | null; metadata?: Record<string, unknown> | null }) {
  return (event.details ?? event.metadata ?? {}) as Record<string, unknown>;
}

function explainEvent(type: string, details: Record<string, unknown>): string | null {
  const reason = typeof details.reason === "string" ? details.reason : null;
  const rule = typeof details.trigger_rule === "string" ? details.trigger_rule : null;
  const current = toNumber(details.current_price ?? details.close_price);
  const stop = toNumber(details.stop_loss);
  const takeProfit = toNumber(details.take_profit);
  const entry = toNumber(details.entry_price);
  const stopPct = toNumber(details.stop_distance_pct);
  const movePct = toNumber(details.price_move_pct);

  if (type.includes("stop_loss")) {
    const parts = [
      "Stop-loss closed the position to cap downside risk.",
      current != null && stop != null
        ? `Price ${formatPrice(current)} reached the stop level ${formatPrice(stop)}${rule ? ` (${rule})` : ""}.`
        : reason,
      entry != null ? `Entry was ${formatPrice(entry)}.` : null,
      stopPct != null ? `Planned stop distance: ${stopPct.toFixed(2)}%.` : null,
      movePct != null ? `Move from entry at close: ${movePct.toFixed(2)}%.` : null,
    ];
    return parts.filter(Boolean).join(" ");
  }

  if (type.includes("take_profit")) {
    const parts = [
      "Take-profit closed the position because the target level was reached.",
      current != null && takeProfit != null
        ? `Price ${formatPrice(current)} reached the target ${formatPrice(takeProfit)}.`
        : reason,
    ];
    return parts.filter(Boolean).join(" ");
  }

  if (type.includes("trailing")) {
    return reason ?? "Trailing stop logic adjusted or closed the position after price moved back from the best seen level.";
  }

  if (type.includes("emergency")) {
    return reason ?? "Emergency risk protection closed or attempted to close the position.";
  }

  if (type.includes("failed") || type.includes("error")) {
    return reason ?? "This lifecycle step failed and may require checking the raw event or logs.";
  }

  return null;
}

function pickMoney(details: Record<string, unknown>, key: string, label: string) {
  const value = toNumber(details[key]);
  return value == null ? null : { label, value: formatCurrency(value) };
}

function pickPrice(details: Record<string, unknown>, key: string, label: string) {
  const value = toNumber(details[key]);
  return value == null ? null : { label, value: formatPrice(value) };
}

function pickNumber(details: Record<string, unknown>, key: string, label: string, suffix = "") {
  const value = toNumber(details[key]);
  return value == null ? null : { label, value: `${value.toFixed(suffix ? 2 : 8)}${suffix}` };
}

function toNumber(value: unknown): number | null {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}
