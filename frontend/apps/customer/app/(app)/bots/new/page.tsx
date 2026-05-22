"use client";

import {
  Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle,
  Input, Label, PageHeader,
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
  Switch,
} from "@ta/ui";
import { cn } from "@ta/utils";
import { ArrowLeft, Loader2, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { SymbolCombobox } from "@/components/bots/symbol-combobox";
import { useExchangeConnections } from "@/lib/hooks/queries/use-exchange-connections";
import { useCreateBot, type CreateBotInput } from "@/lib/hooks/mutations/use-create-bot";
const STRATEGIES: { value: CreateBotInput["strategy"]; label: string; blurb: string }[] = [
  { value: "momentum",        label: "Momentum",        blurb: "Buys breakouts; rides strong trends." },
  { value: "trend_following", label: "Trend following", blurb: "Holds positions while the trend is intact." },
  { value: "scalping",        label: "Scalping",        blurb: "Many small trades, short hold times." },
  { value: "mean_reversion",  label: "Mean reversion",  blurb: "Fades extreme moves back to the mean." },
  { value: "balanced",        label: "Balanced",        blurb: "Mix of momentum and mean reversion." },
];

const SYSTEMS: { value: CreateBotInput["trading_system"]; label: string; blurb: string }[] = [
  { value: "futures_trading", label: "Futures trading", blurb: "Slower RR-based directional trades." },
  { value: "portfolio_management", label: "Portfolio management", blurb: "Small wallet-protection rebalances." },
];

const TIMEFRAMES: CreateBotInput["timeframe"][] = ["1m", "5m", "15m", "1h"];

export default function NewBotPage() {
  const router = useRouter();
  const create = useCreateBot();
  const conns  = useExchangeConnections();

  const [form, setForm] = useState<CreateBotInput>({
    name:                  "BTC Momentum",
    exchange:              "binance",
    symbol:                "BTC/USDT",
    mode:                  "paper",
    trading_system:        "futures_trading",
    strategy:              "momentum",
    risk_level:            "moderate",
    risk_model:            "percentage",
    risk_value:            2,
    risk_reward_ratio:     2,
    max_position_size_pct: 5,
    stop_loss_pct:         2,
    take_profit_pct:       4,
    trailing_stop_pct:     1.5,
    timeframe:             "5m",
  });
  const [error, setError] = useState<string | null>(null);

  const update = <K extends keyof CreateBotInput>(key: K, value: CreateBotInput[K]) =>
    setForm((s) => ({ ...s, [key]: value }));

  // Live mode requires at least one connected exchange that allows trading.
  const liveEligible =
    (conns.data ?? []).some((c) => c.exchange.toLowerCase() === form.exchange && c.is_active && c.can_trade);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!form.name.trim())   return setError("Name is required.");
    if (!form.symbol.trim()) return setError("Trading symbol is required.");
    if (form.mode === "live" && !liveEligible) {
      return setError("Live mode requires a connected exchange with trading enabled. Use paper mode or connect an exchange first.");
    }

    try {
      const bot = await create.mutateAsync({ ...form });
      router.push(`/bots/${bot.id}`);
      router.refresh();
    } catch (e) {
      setError((e as Error).message || "Could not create bot");
    }
  };

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <PageHeader
        title="Create a new bot"
        description="Configure a paper-trading bot. Live mode is only available when an exchange connection is active."
        actions={
          <Link href="/bots">
            <Button size="sm" variant="outline">
              <ArrowLeft className="mr-1.5 h-4 w-4" />
              All bots
            </Button>
          </Link>
        }
      />

      <form onSubmit={onSubmit} className="space-y-6">
        {/* ── Identity ───────────────────────────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Identity</CardTitle>
            <CardDescription>Name, exchange, and the symbol the bot will trade.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="name">Bot name</Label>
              <Input id="name" value={form.name} onChange={(e) => update("name", e.target.value)} maxLength={60} required />
            </div>

            <div className="space-y-1.5">
              <Label>Exchange</Label>
              <Select value={form.exchange} onValueChange={(v) => update("exchange", v as CreateBotInput["exchange"])}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="binance">Binance</SelectItem>
                  <SelectItem value="bybit">Bybit</SelectItem>
                  <SelectItem value="coinbase">Coinbase</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label>Symbol</Label>
              <SymbolCombobox
                value={form.symbol}
                onChange={(internal) => update("symbol", internal)}
              />
              <p className="text-[11px] text-muted-foreground">
                Searchable list of every active Binance USDT spot pair. Cached for 24 hours.
              </p>
            </div>
          </CardContent>
        </Card>

        {/* ── Mode + strategy + risk ─────────────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Strategy</CardTitle>
            <CardDescription>How the bot decides when to enter and exit.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="grid gap-2 sm:grid-cols-2">
              <ModeCard
                label="Paper"
                blurb="Simulated trades against live prices. No exchange required."
                selected={form.mode === "paper"}
                onSelect={() => update("mode", "paper")}
              />
              <ModeCard
                label="Live"
                blurb={liveEligible
                  ? "Real-money execution. Additional gates still apply."
                  : "Connect an exchange with trading enabled to use live mode."}
                disabled={!liveEligible}
                selected={form.mode === "live"}
                onSelect={() => liveEligible && update("mode", "live")}
                badge={
                  liveEligible
                    ? <Badge variant="success">eligible</Badge>
                    : <Badge variant="secondary">no connection</Badge>
                }
              />
            </div>

            <div className="grid gap-2 sm:grid-cols-2">
              {SYSTEMS.map((s) => (
                <button
                  key={s.value}
                  type="button"
                  onClick={() => update("trading_system", s.value)}
                  className={cn(
                    "rounded-lg border bg-card/40 p-3 text-left transition-all hover:bg-accent/40",
                    form.trading_system === s.value && "border-primary bg-primary/10 ring-1 ring-primary/30",
                  )}
                >
                  <div className="text-sm font-medium">{s.label}</div>
                  <div className="text-xs text-muted-foreground">{s.blurb}</div>
                </button>
              ))}
            </div>

            <div className="grid gap-2 md:grid-cols-2">
              {STRATEGIES.map((s) => (
                <button
                  key={s.value}
                  type="button"
                  onClick={() => update("strategy", s.value)}
                  className={cn(
                    "rounded-lg border bg-card/40 p-3 text-left transition-all hover:bg-accent/40",
                    form.strategy === s.value && "border-primary bg-primary/10 ring-1 ring-primary/30",
                  )}
                >
                  <div className="text-sm font-medium">{s.label}</div>
                  <div className="text-xs text-muted-foreground">{s.blurb}</div>
                </button>
              ))}
            </div>

          </CardContent>
        </Card>

        {/* ── Risk model ─────────────────────────────────────────────────── */}
        <Card className="hidden">
          <CardHeader>
            <CardTitle className="text-base">Risk model</CardTitle>
            <CardDescription>How much of the account balance is risked on each trade.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-2 sm:grid-cols-2">
              {(["percentage", "fixed_usd"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => update("risk_model", m)}
                  className={cn(
                    "rounded-lg border bg-card/40 p-3 text-left transition-all hover:bg-accent/40",
                    form.risk_model === m && "border-primary bg-primary/10 ring-1 ring-primary/30",
                  )}
                >
                  <div className="text-sm font-medium">{m === "percentage" ? "Percentage %" : "Fixed USD $"}</div>
                  <div className="text-xs text-muted-foreground">
                    {m === "percentage"
                      ? "Risk a % of your balance each trade (e.g. 2% of $1,000 = $20 risk)"
                      : "Risk a fixed dollar amount each trade (e.g. $50 per trade)"}
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
                onChange={(n) => update("risk_value", n)}
              />
              <NumberField
                label="Risk:reward ratio"
                value={form.risk_reward_ratio}
                step={0.5}
                min={0.5}
                max={10}
                onChange={(n) => update("risk_reward_ratio", n)}
              />
            </div>
            <p className="text-[11px] text-muted-foreground">
              {form.risk_model === "percentage"
                ? `At $1,000 balance: risk $${(1000 * form.risk_value / 100).toFixed(2)} → target $${(1000 * form.risk_value / 100 * form.risk_reward_ratio).toFixed(2)} (1R:${form.risk_reward_ratio}R)`
                : `Risk $${form.risk_value.toFixed(2)} → target $${(form.risk_value * form.risk_reward_ratio).toFixed(2)} (1R:${form.risk_reward_ratio}R)`}
            </p>
          </CardContent>
        </Card>

        {/* ── Position sizing ────────────────────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Sizing &amp; protective stops</CardTitle>
            <CardDescription>Protective stops and signal timeframe. Wallet risk is configured in Settings.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <NumberField label="Stop loss (%)"   value={form.stop_loss_pct}  step={0.1} min={0.1} max={20}
              onChange={(n) => update("stop_loss_pct", n)} />
            <NumberField label="Take profit (%)" value={form.take_profit_pct} step={0.1} min={0.1} max={50}
              onChange={(n) => update("take_profit_pct", n)} />
            <div className="flex items-center justify-between rounded-md border bg-card/40 p-3">
              <div>
                <Label className="text-sm font-medium">Trailing stop</Label>
                <p className="text-xs text-muted-foreground">
                  Tightens the stop as the trade moves in your favour.
                </p>
              </div>
              <Switch
                checked={form.trailing_stop_pct != null}
                onCheckedChange={(v) => update("trailing_stop_pct", v ? 1.5 : null)}
              />
            </div>
            {form.trailing_stop_pct != null ? (
              <NumberField label="Trailing stop (%)" value={form.trailing_stop_pct} step={0.1} min={0.1} max={10}
                onChange={(n) => update("trailing_stop_pct", n)} />
            ) : null}

            <div className="space-y-1.5">
              <Label>Timeframe</Label>
              <Select value={form.timeframe} onValueChange={(v) => update("timeframe", v as CreateBotInput["timeframe"])}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {TIMEFRAMES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>

        {error ? (
          <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-xs">
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            <span>{error}</span>
          </div>
        ) : null}

        <div className="flex items-center justify-end gap-2">
          <Link href="/bots"><Button type="button" variant="ghost">Cancel</Button></Link>
          <Button type="submit" disabled={create.isPending}>
            {create.isPending ? (
              <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Creating bot…</>
            ) : (
              "Create bot"
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

function ModeCard({
  label, blurb, selected, disabled, onSelect, badge,
}: {
  label: string; blurb: string; selected: boolean; disabled?: boolean;
  onSelect: () => void; badge?: React.ReactNode;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onSelect}
      className={cn(
        "rounded-lg border bg-card/40 p-3 text-left transition-all",
        selected   && "border-primary bg-primary/10 ring-1 ring-primary/30",
        disabled   && "cursor-not-allowed opacity-50",
        !disabled  && !selected && "hover:bg-accent/40",
      )}
    >
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium">{label}</div>
        {badge}
      </div>
      <div className="mt-1 text-xs text-muted-foreground">{blurb}</div>
    </button>
  );
}
