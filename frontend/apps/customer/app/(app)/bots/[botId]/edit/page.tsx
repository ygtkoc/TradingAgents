"use client";

import {
  Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle,
  Input, Label, PageHeader,
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
  Skeleton,
  Switch,
} from "@ta/ui";
import { cn } from "@ta/utils";
import { ArrowLeft, Loader2, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { SymbolCombobox } from "@/components/bots/symbol-combobox";
import { useBot }         from "@/lib/hooks/queries/use-bots";
import { useUpdateBot, type UpdateBotInput } from "@/lib/hooks/mutations/use-update-bot";

const STRATEGIES = [
  { value: "momentum",        label: "Momentum",        blurb: "Buys breakouts; rides strong trends." },
  { value: "trend_following", label: "Trend following", blurb: "Holds positions while the trend is intact." },
  { value: "scalping",        label: "Scalping",        blurb: "Many small trades, short hold times." },
  { value: "mean_reversion",  label: "Mean reversion",  blurb: "Fades extreme moves back to the mean." },
  { value: "balanced",        label: "Balanced",        blurb: "Mix of momentum and mean reversion." },
] as const;

const RISK_LEVELS = [
  { value: "conservative", label: "Conservative", blurb: "Small position size, tight stops." },
  { value: "moderate",     label: "Moderate",     blurb: "Default sizing for paper testing." },
  { value: "aggressive",   label: "Aggressive",   blurb: "Larger size, wider stops." },
] as const;

const SYSTEMS = [
  { value: "futures_trading", label: "Futures trading", blurb: "Slower RR-based directional trades." },
  { value: "portfolio_management", label: "Portfolio management", blurb: "Small wallet-protection rebalances." },
] as const;

const TIMEFRAMES = ["1m", "5m", "15m", "1h"] as const;

interface EditForm {
  name:                  string;
  symbol:                string;
  trading_system:        "futures_trading" | "portfolio_management";
  strategy_type:         string;
  risk_level:            "conservative" | "moderate" | "aggressive";
  risk_model:            "percentage" | "fixed_usd";
  risk_value:            number;
  risk_reward_ratio:     number;
  max_position_size_pct: number;
  stop_loss_pct:         number;
  take_profit_pct:       number;
  trailing_stop_pct:     number | null;
  timeframe:             "1m" | "5m" | "15m" | "1h";
  requires_manual_approval: boolean;
}

export default function BotEditPage() {
  const params = useParams<{ botId: string }>();
  const botId  = params.botId;
  const router = useRouter();

  const { data: bot, isLoading } = useBot(botId);
  const update = useUpdateBot(botId);

  const [form, setForm]   = useState<EditForm | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // Populate form once bot loads
  useEffect(() => {
    if (!bot || form) return;
    const meta = bot.metadata ?? {};
    setForm({
      name:                  bot.name,
      symbol:                bot.trading_pairs?.[0] ?? "BTC/USDT",
      trading_system:        (meta.trading_system as EditForm["trading_system"] | undefined) ?? "futures_trading",
      strategy_type:         bot.strategy_type ?? (meta.strategy as string | undefined) ?? "balanced",
      risk_level:            (meta.risk_level as EditForm["risk_level"] | undefined) ?? "moderate",
      risk_model:            (bot.risk_model as EditForm["risk_model"]) ?? "percentage",
      risk_value:            bot.risk_value   ?? 2,
      risk_reward_ratio:     bot.risk_reward_ratio ?? 2,
      max_position_size_pct: bot.max_position_size_pct ?? 5,
      stop_loss_pct:         (meta.stop_loss_pct   as number | undefined) ?? 2,
      take_profit_pct:       (meta.take_profit_pct as number | undefined) ?? 4,
      trailing_stop_pct:     (meta.trailing_stop_pct as number | null | undefined) ?? null,
      timeframe:             (meta.timeframe as EditForm["timeframe"] | undefined) ?? "5m",
      requires_manual_approval: bot.requires_manual_approval ?? false,
    });
  }, [bot, form]);

  const update_ = <K extends keyof EditForm>(key: K, value: EditForm[K]) =>
    setForm((s) => s ? { ...s, [key]: value } : s);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!form) return;
    setError(null);
    setSaved(false);

    if (!form.name.trim()) return setError("Name is required.");

    const patch: UpdateBotInput = {
      name:                  form.name.trim(),
      strategy_type:         form.strategy_type,
      risk_model:            form.risk_model,
      risk_value:            form.risk_value,
      risk_reward_ratio:     form.risk_reward_ratio,
      max_position_size_pct: form.max_position_size_pct,
      stop_loss_pct:         form.stop_loss_pct,
      take_profit_pct:       form.take_profit_pct,
      trailing_stop_pct:     form.trailing_stop_pct,
      timeframe:             form.timeframe,
      risk_level:            form.risk_level,
      trading_system:        form.trading_system,
      requires_manual_approval: form.requires_manual_approval,
    };

    try {
      await update.mutateAsync(patch);
      setSaved(true);
      router.push(`/bots/${botId}`);
      router.refresh();
    } catch (e) {
      setError((e as Error).message || "Could not update bot");
    }
  };

  if (isLoading || !form) {
    return (
      <div className="mx-auto flex max-w-3xl flex-col gap-6">
        <Skeleton className="h-9 w-64 rounded-xl" />
        <Skeleton className="h-64 w-full rounded-2xl" />
        <Skeleton className="h-48 w-full rounded-2xl" />
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <PageHeader
        title={`Edit: ${bot?.name ?? "Bot"}`}
        description="Update this bot's strategy, risk model, and sizing parameters."
        actions={
          <Link href={`/bots/${botId}`}>
            <Button size="sm" variant="outline">
              <ArrowLeft className="mr-1.5 h-4 w-4" />
              Back to bot
            </Button>
          </Link>
        }
      />

      <form onSubmit={onSubmit} className="space-y-6">
        {/* ── Identity ─────────────────────────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle>Identity</CardTitle>
            <CardDescription>Bot name and the symbol it trades.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="name">Bot name</Label>
              <Input
                id="name"
                value={form.name}
                onChange={(e) => update_("name", e.target.value)}
                maxLength={60}
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label>Symbol</Label>
              <SymbolCombobox
                value={form.symbol}
                onChange={(v) => update_("symbol", v)}
              />
              <p className="text-[11px] text-muted-foreground">
                Note: changing the symbol resets warmup for this bot.
              </p>
            </div>
            <div className="space-y-1.5">
              <Label>Timeframe</Label>
              <Select
                value={form.timeframe}
                onValueChange={(v) => update_("timeframe", v as EditForm["timeframe"])}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {TIMEFRAMES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>

        {/* ── Strategy ─────────────────────────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle>Strategy</CardTitle>
            <CardDescription>How the bot decides when to enter and exit.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-2 md:grid-cols-2">
              {SYSTEMS.map((s) => (
                <button
                  key={s.value}
                  type="button"
                  onClick={() => update_("trading_system", s.value)}
                  className={cn(
                    "rounded-xl border bg-card/40 px-4 py-3 text-left transition-all hover:border-border hover:bg-card/60",
                    form.trading_system === s.value && "border-primary/40 bg-primary/8 ring-1 ring-primary/20",
                  )}
                >
                  <div className="text-[13px] font-semibold text-foreground">{s.label}</div>
                  <div className="mt-0.5 text-[11px] text-muted-foreground">{s.blurb}</div>
                </button>
              ))}
            </div>

            <div className="grid gap-2 md:grid-cols-2">
              {STRATEGIES.map((s) => (
                <button
                  key={s.value}
                  type="button"
                  onClick={() => update_("strategy_type", s.value)}
                  className={cn(
                    "rounded-xl border bg-card/40 px-4 py-3 text-left transition-all hover:border-border hover:bg-card/60",
                    form.strategy_type === s.value && "border-primary/40 bg-primary/8 ring-1 ring-primary/20",
                  )}
                >
                  <div className="text-[13px] font-semibold text-foreground">{s.label}</div>
                  <div className="mt-0.5 text-[11px] text-muted-foreground">{s.blurb}</div>
                </button>
              ))}
            </div>

            <div className="hidden">
              {RISK_LEVELS.map((r) => (
                <button
                  key={r.value}
                  type="button"
                  onClick={() => update_("risk_level", r.value)}
                  className={cn(
                    "rounded-xl border bg-card/40 px-4 py-3 text-left transition-all hover:border-border hover:bg-card/60",
                    form.risk_level === r.value && "border-primary/40 bg-primary/8 ring-1 ring-primary/20",
                  )}
                >
                  <div className="text-[13px] font-semibold text-foreground">{r.label}</div>
                  <div className="mt-0.5 text-[11px] text-muted-foreground">{r.blurb}</div>
                </button>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* ── Risk model ───────────────────────────────────────────────── */}
        <Card className="hidden">
          <CardHeader>
            <CardTitle>Risk model</CardTitle>
            <CardDescription>How much of the account balance is risked on each trade.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-2 sm:grid-cols-2">
              {(["percentage", "fixed_usd"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => update_("risk_model", m)}
                  className={cn(
                    "rounded-xl border bg-card/40 px-4 py-3 text-left transition-all hover:border-border hover:bg-card/60",
                    form.risk_model === m && "border-primary/40 bg-primary/8 ring-1 ring-primary/20",
                  )}
                >
                  <div className="text-[13px] font-semibold text-foreground">{m === "percentage" ? "Percentage %" : "Fixed USD $"}</div>
                  <div className="mt-0.5 text-[11px] text-muted-foreground">
                    {m === "percentage"
                      ? "Risk a % of your balance each trade"
                      : "Risk a fixed dollar amount each trade"}
                  </div>
                </button>
              ))}
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <NumberField
                label={form.risk_model === "percentage" ? "Risk per trade (%)" : "Risk per trade ($)"}
                value={form.risk_value}
                step={form.risk_model === "percentage" ? 0.1 : 1}
                min={form.risk_model === "percentage" ? 0.1 : 1}
                max={form.risk_model === "percentage" ? 10 : 10000}
                onChange={(n) => update_("risk_value", n)}
              />
              <NumberField
                label="Risk:reward ratio"
                value={form.risk_reward_ratio}
                step={0.5}
                min={0.5}
                max={10}
                onChange={(n) => update_("risk_reward_ratio", n)}
              />
            </div>
            <p className="text-[11px] text-muted-foreground">
              {form.risk_model === "percentage"
                ? `At $1,000 balance: risk $${(1000 * form.risk_value / 100).toFixed(2)} → target $${(1000 * form.risk_value / 100 * form.risk_reward_ratio).toFixed(2)}`
                : `Risk $${form.risk_value.toFixed(2)} → target $${(form.risk_value * form.risk_reward_ratio).toFixed(2)}`}
            </p>
          </CardContent>
        </Card>

        {/* ── Position sizing ──────────────────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle>Sizing &amp; protective stops</CardTitle>
            <CardDescription>Protective stops and signal timeframe. Wallet risk and max R are configured in Settings.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <NumberField
              label="Stop loss (%)"
              value={form.stop_loss_pct}
              step={0.1} min={0.1} max={20}
              onChange={(n) => update_("stop_loss_pct", n)}
            />
            <div className="flex items-center justify-between rounded-xl border border-border/40 bg-card/40 p-4">
              <div>
                <Label className="text-[13px] font-medium">Trailing stop</Label>
                <p className="text-[12px] text-muted-foreground">
                  Tightens the stop as the trade moves in your favour.
                </p>
              </div>
              <Switch
                checked={form.trailing_stop_pct != null}
                onCheckedChange={(v) => update_("trailing_stop_pct", v ? 1.5 : null)}
              />
            </div>
            {form.trailing_stop_pct != null ? (
              <NumberField
                label="Trailing stop (%)"
                value={form.trailing_stop_pct}
                step={0.1} min={0.1} max={10}
                onChange={(n) => update_("trailing_stop_pct", n)}
              />
            ) : null}
          </CardContent>
        </Card>

        {/* ── Approval ─────────────────────────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle>Approval</CardTitle>
            <CardDescription>Require manual review before trades are executed.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between rounded-xl border border-border/40 bg-card/40 p-4">
              <div>
                <Label className="text-[13px] font-medium">Manual approval required</Label>
                <p className="text-[12px] text-muted-foreground">
                  Every trade decision must be approved in the dashboard before execution.
                </p>
              </div>
              <Switch
                checked={form.requires_manual_approval}
                onCheckedChange={(v) => update_("requires_manual_approval", v)}
              />
            </div>
            {bot?.mode === "live" && !form.requires_manual_approval && (
              <p className="mt-2 text-xs text-warning">
                ⚠️ Live bots without manual approval execute trades automatically.
              </p>
            )}
          </CardContent>
        </Card>

        {error ? (
          <div className="flex items-start gap-3 rounded-xl border border-destructive/30 bg-destructive/8 p-4 text-[13px] backdrop-blur-sm">
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            <span className="text-destructive">{error}</span>
          </div>
        ) : null}

        {saved ? (
          <div className="rounded-xl border border-success/30 bg-success/8 p-4 text-[13px] text-success backdrop-blur-sm">
            Bot updated successfully.
          </div>
        ) : null}

        <div className="flex items-center justify-end gap-2">
          <Link href={`/bots/${botId}`}>
            <Button type="button" variant="ghost">Cancel</Button>
          </Link>
          <Button type="submit" disabled={update.isPending}>
            {update.isPending ? (
              <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Saving…</>
            ) : (
              "Save changes"
            )}
          </Button>
        </div>
      </form>
    </div>
  );
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function NumberField({
  label, value, onChange, min, max, step,
}: {
  label: string; value: number; onChange: (n: number) => void;
  min?: number; max?: number; step?: number;
}) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <Input
        type="number"
        inputMode="decimal"
        value={Number.isFinite(value) ? value : 0}
        min={min} max={max} step={step}
        onChange={(e) => {
          const n = Number(e.target.value);
          if (Number.isFinite(n)) onChange(n);
        }}
      />
    </div>
  );
}
