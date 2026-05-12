"use client";

import { Card, CardContent, CardHeader, CardTitle, EmptyState, ErrorState, Skeleton } from "@ta/ui";
import { formatDateTime } from "@ta/utils";

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
        <CardTitle>Timeline</CardTitle>
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
                <span className="absolute -left-[1.4rem] top-1 inline-block h-2 w-2 rounded-full bg-primary" />
                <div className="text-xs text-muted-foreground">
                  {formatDateTime(e.created_at)}
                </div>
                <div className="text-sm font-medium">{e.event_type}</div>
                {Object.keys(e.details ?? {}).length > 0 ? (
                  <pre className="mt-1 overflow-auto rounded bg-muted/40 p-2 text-[11px]">
                    {JSON.stringify(e.details, null, 2)}
                  </pre>
                ) : null}
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
