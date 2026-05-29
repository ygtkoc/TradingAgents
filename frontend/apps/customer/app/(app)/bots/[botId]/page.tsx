"use client";

import {
  Badge,
  Button,
  Card, CardContent, CardDescription, CardHeader, CardTitle,
  EmptyState,
  ErrorState,
  PageHeader,
  ProductPage,
  Progress,
  Skeleton,
  Tabs, TabsContent, TabsList, TabsTrigger,
} from "@ta/ui";
import { cn, formatRelative } from "@ta/utils";
import {
  Bot, CheckCircle2, Clock, Edit, Radar, RefreshCw, Settings,
  TrendingUp, Zap,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { RecentDecisionsTable } from "@/components/dashboard/recent-decisions-table";
import { RecentTradesTable }    from "@/components/dashboard/recent-trades-table";
import { useAgentRuns }         from "@/lib/hooks/queries/use-agent-runs";
import { useBot }               from "@/lib/hooks/queries/use-bots";

const STRATEGY_LABEL: Record<string, string> = {
  scalping:        "Scalping",
  momentum:        "Momentum",
  trend_following: "Trend Following",
  mean_reversion:  "Mean Reversion",
  balanced:        "Balanced",
};

export default function BotDetailPage() {
  const params = useParams<{ botId: string }>();
  const botId  = params.botId;
  const { data: bot, isLoading, isError, refetch, isFetching } = useBot(botId);
  const runs   = useAgentRuns({ botId, limit: 25 });

  if (isError) return <ErrorState onRetry={() => void refetch()} />;

  if (isLoading || !bot) {
    return (
      <ProductPage size="xl">
        <Skeleton className="h-9 w-64 rounded-xl" />
        <Skeleton className="h-40 w-full rounded-2xl" />
        <Skeleton className="h-64 w-full rounded-2xl" />
      </ProductPage>
    );
  }

  const warmupStatus    = bot.warmup_status ?? "pending";
  const candlesCollected = bot.candles_collected ?? 0;
  const candlesRequired  = bot.candles_required  ?? 100;
  const warmupPct = candlesRequired > 0
    ? Math.min(100, Math.round((candlesCollected / candlesRequired) * 100))
    : 100;

  const isActive   = bot.status === "active";
  const isReady    = warmupStatus === "ready";

  return (
    <ProductPage size="xl">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <PageHeader
        eyebrow="Agent detail"
        title={bot.name}
        description={`${bot.mode.toUpperCase()} · Created ${formatRelative(bot.created_at)}`}
        actions={
          <div className="flex items-center gap-2">
            {isFetching && (
              <RefreshCw className="h-3.5 w-3.5 animate-spin text-muted-foreground/40" />
            )}
            <Badge
              variant={isActive ? "success" : bot.status === "paused" ? "warning" : "secondary"}
              className="gap-1"
            >
              {isActive && (
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-60" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-success" />
                </span>
              )}
              {bot.status}
            </Badge>
            <Link href={`/bots/${botId}/edit`}>
              <Button size="sm" variant="outline" className="gap-1.5">
                <Edit className="h-3.5 w-3.5" /> Edit
              </Button>
            </Link>
          </div>
        }
      />

      {/* ── Warmup + Stats hero ─────────────────────────────────────────────── */}
      <div className={cn(
        "relative overflow-hidden rounded-2xl border p-6 backdrop-blur-sm",
        isReady
          ? "border-success/20 bg-gradient-to-br from-success/5 via-card to-card"
          : warmupStatus === "warming_up"
            ? "border-warning/20 bg-gradient-to-br from-warning/5 via-card to-card"
            : "border-border/50 bg-card/80",
      )}>
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className={cn(
              "flex h-12 w-12 items-center justify-center rounded-2xl border",
              isReady ? "border-success/20 bg-success/10" : "border-border/40 bg-card/60",
            )}>
              {isReady ? <CheckCircle2 className="h-6 w-6 text-success" />
                       : <Radar className="h-6 w-6 text-muted-foreground" />}
            </div>
            <div>
              <div className="text-[15px] font-semibold text-foreground">
                {isReady ? "Ready to trade"
                  : warmupStatus === "warming_up" ? "Warming up"
                  : "Warmup pending"}
              </div>
              <div className="text-[13px] text-muted-foreground">
                {isReady
                  ? "Enough candles collected. Signals will fire per strategy cadence."
                  : warmupStatus === "warming_up"
                    ? `${candlesCollected} / ${candlesRequired} candles — trading paused until complete.`
                    : "Will start collecting candles when the engine activates."}
              </div>
            </div>
          </div>

          {/* Scan times */}
          <div className="flex flex-col items-end gap-1 shrink-0 text-[12px]">
            {bot.last_signal_at ? (
              <div className="flex items-center gap-1 text-muted-foreground">
                <Clock className="h-3 w-3" />
                <span>Last scan {formatRelative(bot.last_signal_at)}</span>
              </div>
            ) : null}
            {bot.next_signal_at ? (
              <div className="flex items-center gap-1 text-primary">
                <Zap className="h-3 w-3" />
                <span>
                  Next {new Date(bot.next_signal_at) > new Date()
                    ? formatRelative(bot.next_signal_at) : "due now"}
                </span>
              </div>
            ) : null}
          </div>
        </div>

        {/* Progress bar (only if warming up) */}
        {warmupStatus !== "ready" && (
          <div className="mt-4 space-y-1.5">
            <div className="flex justify-between text-[11px] text-muted-foreground/60">
              <span>{candlesCollected} collected</span>
              <span>{warmupPct}% · {candlesRequired} required</span>
            </div>
            <Progress
                value={warmupPct}
                className="h-1.5"
                barClassName={warmupStatus === "warming_up" ? "bg-warning" : "bg-muted-foreground/30"}
              />
          </div>
        )}

        {/* Symbols */}
        {bot.trading_pairs.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-1.5">
            {bot.trading_pairs.map((p) => (
              <span key={p} className="rounded-lg border border-border/50 bg-card/60 px-2 py-0.5 font-mono text-[11px] text-foreground">
                {p}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* ── Tabs ─────────────────────────────────────────────────────────────── */}
      <Tabs defaultValue="overview">
        <TabsList className="rounded-xl border border-border/40 bg-card/60 p-1">
          {["overview","trades","decisions","agent-runs"].map((t) => (
            <TabsTrigger
              key={t}
              value={t}
              className="rounded-lg text-[12px] font-medium capitalize data-[state=active]:bg-primary/10 data-[state=active]:text-primary"
            >
              {t.replace("-", " ")}
            </TabsTrigger>
          ))}
        </TabsList>

        {/* Overview tab */}
        <TabsContent value="overview" className="mt-4">
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Settings className="h-4 w-4 text-muted-foreground/50" />
                <CardTitle>Configuration</CardTitle>
              </div>
              <CardDescription>Strategy settings for this bot. Wallet risk is configured in Settings.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {[
                  { label: "Strategy",           value: STRATEGY_LABEL[bot.strategy_type ?? ""] ?? bot.strategy_type ?? "—" },
                  { label: "Max positions",      value: String(bot.max_open_positions) },
                  { label: "Max daily loss",     value: `${bot.max_daily_loss_pct}%` },
                  { label: "Trailing stop",      value: bot.trailing_stop_pct ?? (bot.metadata?.trailing_stop_pct as number | undefined) ?? "—" },
                  { label: "Manual approval",    value: bot.requires_manual_approval ? "Required" : "Auto" },
                  { label: "Exchange",           value: bot.exchange_account_id ? "Linked" : "None" },
                ].map(({ label, value }) => (
                  <div key={label} className="rounded-xl border border-border/30 bg-card/40 px-4 py-3">
                    <div className="text-[9px] font-semibold uppercase tracking-[0.12em] text-muted-foreground/50">{label}</div>
                    <div className="mt-1 text-[13px] font-medium text-foreground">{String(value)}</div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="trades" className="mt-4">
          <Card>
            <CardContent className="pt-5">
              <RecentTradesTable limit={50} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="decisions" className="mt-4">
          <Card>
            <CardContent className="pt-5">
              <RecentDecisionsTable limit={50} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="agent-runs" className="mt-4">
          <Card>
            <CardContent className="pt-5">
              {runs.isLoading ? (
                <Skeleton className="h-40 w-full rounded-xl" />
              ) : (runs.data ?? []).length === 0 ? (
                <EmptyState title="No agent runs yet" />
              ) : (
                <ol className="space-y-2">
                  {(runs.data ?? []).map((r) => (
                    <li
                      key={r.id}
                      className="flex items-center justify-between rounded-xl border border-border/30 bg-card/40 px-4 py-3 text-[13px]"
                    >
                      <div>
                        <div className="font-mono text-[11px] text-muted-foreground/60">{r.id.slice(0, 10)}…</div>
                        <div className="font-medium text-foreground">{(r.final_decision ?? "—").replace(/_/g, " ")}</div>
                      </div>
                      <div className="text-right text-[11px] text-muted-foreground">
                        <div className={cn(
                          "font-semibold",
                          r.status === "completed" ? "text-success" : r.status === "failed" ? "text-destructive" : "text-muted-foreground",
                        )}>
                          {r.status}
                        </div>
                        <div>{formatRelative(r.started_at)}</div>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </ProductPage>
  );
}
