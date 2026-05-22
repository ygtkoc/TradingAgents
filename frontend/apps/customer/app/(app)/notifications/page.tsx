"use client";

import {
  Button,
  Card, CardContent,
  EmptyState,
  ErrorState,
  PageHeader,
  Skeleton,
} from "@ta/ui";
import { cn, formatRelative } from "@ta/utils";
import { Bell, Check } from "lucide-react";
import { useRouter } from "next/navigation";

import { useNotifications }      from "@/lib/hooks/queries/use-notifications";
import { useNotificationMutations } from "@/lib/hooks/mutations/use-notification-mutations";

export default function NotificationsPage() {
  const router = useRouter();
  const { data, isLoading, isError, refetch } = useNotifications(100);
  const { markRead, markAllRead } = useNotificationMutations();

  const unreadCount = (data ?? []).filter((n) => !n.read).length;

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-5">
      <PageHeader
        title="Notifications"
        description="Realtime updates from the Agent, Execution, and Position engines."
        actions={
          <Button
            size="sm"
            variant="outline"
            disabled={markAllRead.isPending || unreadCount === 0}
            onClick={() => markAllRead.mutate()}
            className="gap-1.5"
          >
            <Check className="h-3.5 w-3.5" />
            Mark all read
            {unreadCount > 0 && (
              <span className="ml-0.5 rounded-full bg-primary/20 px-1.5 text-[10px] font-bold text-primary">
                {unreadCount}
              </span>
            )}
          </Button>
        }
      />

      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}

      <Card>
        <CardContent className="pt-5">
          {isLoading ? (
            <div className="space-y-2.5">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-16 w-full rounded-xl" />
              ))}
            </div>
          ) : !data || data.length === 0 ? (
            <EmptyState
              icon={Bell}
              title="No notifications"
              description="You're all caught up. Alerts from agents and the execution engine appear here."
            />
          ) : (
            <ul className="space-y-1.5">
              {data.map((n) => {
                const opensTrade = n.related_table === "trades" && Boolean(n.related_id);
                const openTrade = () => {
                  if (opensTrade && n.related_id) router.push(`/trades/${n.related_id}`);
                };

                return (
                  <li
                      key={n.id}
                      role={opensTrade ? "button" : undefined}
                      tabIndex={opensTrade ? 0 : undefined}
                      onClick={openTrade}
                      onKeyDown={(event) => {
                        if (!opensTrade) return;
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          openTrade();
                        }
                      }}
                      className={cn(
                        "flex items-start gap-3 rounded-xl border px-4 py-3 text-[13px] transition-colors",
                        opensTrade && "cursor-pointer hover:border-primary/30 hover:bg-primary/5",
                        !n.read
                          ? "border-primary/15 bg-primary/5"
                          : "border-border/30 bg-card/40",
                      )}
                    >
                      <span
                        className={cn(
                          "mt-1 inline-flex h-2 w-2 shrink-0 rounded-full",
                          n.read ? "bg-muted-foreground/20" : "bg-primary animate-pulse",
                        )}
                        aria-hidden
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-start justify-between gap-2">
                          <span className="font-semibold text-foreground leading-tight">
                            {n.title}
                          </span>
                          <span className="shrink-0 text-[11px] text-muted-foreground/60">
                            {formatRelative(n.created_at)}
                          </span>
                        </div>
                        <p className="mt-0.5 text-[12px] leading-relaxed text-muted-foreground">
                          {n.body}
                        </p>
                        {!n.read ? (
                          <Button
                            size="sm"
                            variant="ghost"
                            className="mt-1 h-6 px-2 text-[11px] text-muted-foreground"
                            disabled={markRead.isPending}
                            onClick={(event) => {
                              event.stopPropagation();
                              markRead.mutate([n.id]);
                            }}
                          >
                            Mark read
                          </Button>
                        ) : null}
                      </div>
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
