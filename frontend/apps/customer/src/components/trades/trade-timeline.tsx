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
                <EventDetails details={e.details ?? {}} />
                {Object.keys(e.details ?? {}).length > 0 ? (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-[11px] text-muted-foreground hover:text-foreground">
                      Raw event data
                    </summary>
                    <pre className="mt-1 overflow-auto rounded bg-muted/40 p-2 text-[11px]">
                      {JSON.stringify(e.details, null, 2)}
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

function EventDetails({ details }: { details: Record<string, unknown> }) {
  const fields = [
    pickPrice(details, "fill_price", "Fill"),
    pickPrice(details, "entry_price", "Entry"),
    pickPrice(details, "current_price", "Price"),
    pickPrice(details, "close_price", "Close"),
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
