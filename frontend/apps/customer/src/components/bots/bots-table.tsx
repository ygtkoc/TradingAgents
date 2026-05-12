"use client";

import {
  Badge, Button, EmptyState, ErrorState, Progress,
} from "@ta/ui";
import { cn, formatCurrency, formatRelative } from "@ta/utils";
import type { Bot } from "@ta/types";
import {
  Archive, Bot as BotIcon, ChevronRight, Cpu, Pause, Play,
  Radar, TrendingUp, Zap,
} from "lucide-react";
import Link from "next/link";

import { useBots }         from "@/lib/hooks/queries/use-bots";
import { useTrades }       from "@/lib/hooks/queries/use-trades";
import { useBotMutations } from "@/lib/hooks/mutations/use-bot-mutations";

// ── Color map by strategy ────────────────────────────────────────────────────
const STRATEGY_COLORS: Record<string, string> = {
  scalping:        "text-primary   bg-primary/10   border-primary/20",
  momentum:        "text-success   bg-success/10   border-success/20",
  trend_following: "text-violet-400 bg-violet-400/10 border-violet-400/20",
  mean_reversion:  "text-amber-400  bg-amber-400/10  border-amber-400/20",
  balanced:        "text-sky-400    bg-sky-400/10    border-sky-400/20",
};

const STRATEGY_LABEL: Record<string, string> = {
  scalping:        "Scalping",
  momentum:        "Momentum",
  trend_following: "Trend",
  mean_reversion:  "Mean Rev.",
  balanced:        "Balanced",
};

const STATUS_META = {
  active:   { dot: "bg-success animate-pulse", text: "text-success",        label: "Active" },
  paused:   { dot: "bg-warning",               text: "text-warning",        label: "Paused" },
  inactive: { dot: "bg-muted-foreground/30",   text: "text-muted-foreground", label: "Inactive" },
  archived: { dot: "bg-muted-foreground/20",   text: "text-muted-foreground", label: "Archived" },
  error:    { dot: "bg-destructive",           text: "text-destructive",    label: "Error" },
} as const;

// ── Single bot card ──────────────────────────────────────────────────────────
function BotCard({ bot, pnl, openTrades }: { bot: Bot; pnl: number; openTrades: number }) {
  const { start, pause, archive } = useBotMutations();

  const status     = (STATUS_META[bot.status as keyof typeof STATUS_META] ?? STATUS_META.inactive);
  const warmup     = bot.warmup_status ?? "pending";
  const req        = bot.candles_required  ?? 100;
  const collected  = bot.candles_collected ?? 0;
  const warmupPct  = warmup === "ready" ? 100 : req > 0 ? Math.min(100, Math.round((collected / req) * 100)) : 0;
  const strategy   = bot.strategy_type ?? "balanced";
  const stratColor = STRATEGY_COLORS[strategy] ?? STRATEGY_COLORS.balanced;

  const busy =
    (start.isPending   && start.variables   === bot.id) ||
    (pause.isPending   && pause.variables   === bot.id) ||
    (archive.isPending && archive.variables === bot.id);

  return (
    <div className={cn(
      "group relative flex flex-col overflow-hidden rounded-2xl border bg-card/80 backdrop-blur-sm",
      "transition-all duration-200 hover:border-border hover:shadow-[0_4px_20px_rgba(0,0,0,0.4)]",
      bot.status === "active" ? "border-success/20 shadow-[0_0_0_1px_hsl(158_72%_42%/0.1)]" : "border-border/50",
      bot.is_archived ? "opacity-60" : "",
    )}>
      {/* Gradient backdrop for active bots */}
      {bot.status === "active" && (
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_left,hsl(158_72%_42%/0.05),transparent_60%)]" />
      )}

      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="relative flex items-start justify-between p-4 pb-3">
        {/* Bot icon + name */}
        <div className="flex items-center gap-3">
          <div className={cn(
            "flex h-10 w-10 items-center justify-center rounded-xl border text-[13px] font-bold",
            stratColor,
          )}>
            <BotIcon className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <Link
              href={`/bots/${bot.id}`}
              className="block truncate font-semibold text-[14px] text-foreground hover:text-primary transition-colors"
            >
              {bot.name}
            </Link>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className={cn(
                "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold",
                stratColor,
              )}>
                {STRATEGY_LABEL[strategy] ?? strategy}
              </span>
              <span className="text-[11px] text-muted-foreground/60">·</span>
              <span className="text-[11px] text-muted-foreground/60 font-mono">{bot.mode}</span>
            </div>
          </div>
        </div>

        {/* Status dot */}
        <div className="flex items-center gap-1.5 shrink-0">
          <span className={cn("h-2 w-2 rounded-full shrink-0", status.dot)} />
          <span className={cn("text-[11px] font-semibold", status.text)}>{status.label}</span>
        </div>
      </div>

      {/* ── Stats row ───────────────────────────────────────────────────── */}
      <div className="relative grid grid-cols-3 gap-px bg-border/20 mx-0">
        <StatCell label="P&L"         value={formatCurrency(pnl)}    tone={pnl > 0 ? "pos" : pnl < 0 ? "neg" : null} />
        <StatCell label="Open trades" value={String(openTrades)} />
        <StatCell label="Symbols"     value={String((bot.trading_pairs ?? []).length)} />
      </div>

      {/* ── Warmup progress ─────────────────────────────────────────────── */}
      <div className="relative px-4 py-3 border-t border-border/20">
        <div className="flex items-center justify-between text-[11px] mb-1.5">
          <div className="flex items-center gap-1 text-muted-foreground">
            <Radar className="h-3 w-3" />
            <span>Warmup: {warmup === "ready" ? "ready" : warmup === "warming_up" ? `${collected}/${req}` : "pending"}</span>
          </div>
          <span className={cn(
            "font-semibold",
            warmup === "ready"      ? "text-success"
            : warmup === "warming_up" ? "text-warning"
            : "text-muted-foreground",
          )}>
            {warmupPct}%
          </span>
        </div>
        <Progress
          value={warmupPct}
          className="h-1"
          barClassName={
            warmup === "ready"       ? "bg-success"
            : warmup === "warming_up" ? "bg-warning"
            : "bg-muted-foreground/30"
          }
        />
        {bot.next_signal_at && warmup === "ready" ? (
          <div className="mt-1.5 flex items-center gap-1 text-[10px] text-muted-foreground/50">
            <Zap className="h-2.5 w-2.5" />
            <span>Next signal {formatRelative(bot.next_signal_at)}</span>
          </div>
        ) : null}
      </div>

      {/* ── Actions ─────────────────────────────────────────────────────── */}
      <div className="relative flex items-center gap-1.5 border-t border-border/20 bg-card/40 px-4 py-2.5">
        {bot.status === "active" ? (
          <Button
            size="sm"
            variant="outline"
            className="h-7 gap-1.5 text-[11px]"
            disabled={busy}
            onClick={(e) => { e.stopPropagation(); pause.mutate(bot.id); }}
          >
            <Pause className="h-3 w-3" /> Pause
          </Button>
        ) : (
          <Button
            size="sm"
            variant="outline"
            className="h-7 gap-1.5 text-[11px]"
            disabled={busy || bot.is_archived}
            onClick={(e) => { e.stopPropagation(); start.mutate(bot.id); }}
          >
            <Play className="h-3 w-3" /> Start
          </Button>
        )}
        <Button
          size="sm"
          variant="ghost"
          className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
          disabled={busy || bot.is_archived}
          onClick={(e) => { e.stopPropagation(); archive.mutate(bot.id); }}
          aria-label="Archive bot"
        >
          <Archive className="h-3.5 w-3.5" />
        </Button>

        {/* Detail link */}
        <Link
          href={`/bots/${bot.id}`}
          className="ml-auto flex items-center gap-1 text-[11px] text-muted-foreground/60 hover:text-foreground transition-colors"
        >
          Details
          <ChevronRight className="h-3.5 w-3.5" />
        </Link>
      </div>
    </div>
  );
}

function StatCell({ label, value, tone }: { label: string; value: string; tone?: "pos" | "neg" | null }) {
  return (
    <div className="flex flex-col gap-0.5 bg-card/60 px-3 py-2.5">
      <span className="text-[9px] font-semibold uppercase tracking-[0.12em] text-muted-foreground/50">{label}</span>
      <span className={cn(
        "text-[13px] font-bold tabular-nums",
        tone === "pos" ? "text-success" : tone === "neg" ? "text-destructive" : "text-foreground",
      )}>
        {value}
      </span>
    </div>
  );
}

// ── Main component ───────────────────────────────────────────────────────────
export function BotsTable() {
  const bots    = useBots();
  const trades  = useTrades({ limit: 500 });

  const rows = (bots.data ?? []).map((b) => {
    const own = (trades.data ?? []).filter((t) => t.bot_id === b.id);
    return {
      bot:        b,
      pnl:        own.reduce((s, t) => s + (t.realized_pnl ?? t.unrealized_pnl ?? 0), 0),
      openTrades: own.filter((t) => t.status === "open").length,
    };
  });

  if (bots.isError) {
    return <ErrorState onRetry={() => void bots.refetch()} />;
  }

  if (bots.isLoading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-56 rounded-2xl border border-border/50 bg-card/60 shimmer" />
        ))}
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border/50 bg-card/40 p-12">
        <EmptyState
          title="No bots yet"
          description="Create your first bot to start the autonomous trading pipeline."
          icon={Cpu}
        />
      </div>
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {rows.map(({ bot, pnl, openTrades }) => (
        <BotCard key={bot.id} bot={bot} pnl={pnl} openTrades={openTrades} />
      ))}
    </div>
  );
}
