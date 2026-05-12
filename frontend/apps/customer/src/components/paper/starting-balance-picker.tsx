"use client";

import { Button, Input, Label } from "@ta/ui";
import { cn, formatCurrency } from "@ta/utils";
import { useState } from "react";

const PRESETS = [100, 500, 1000, 5000] as const;

interface Props {
  defaultValue?: number;
  onConfirm: (amount: number) => void;
  ctaLabel?:  string;
  busy?:      boolean;
}

export function StartingBalancePicker({
  defaultValue = 1000,
  onConfirm,
  ctaLabel = "Continue",
  busy,
}: Props) {
  const [value, setValue] = useState<number>(defaultValue);
  const [custom, setCustom] = useState<string>("");

  const useCustom = !PRESETS.includes(value as (typeof PRESETS)[number]);

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {PRESETS.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => { setValue(p); setCustom(""); }}
            className={cn(
              "rounded-xl border px-4 py-3 text-left transition-all",
              "bg-card/40 backdrop-blur-sm hover:bg-accent/40",
              value === p && !useCustom
                ? "border-primary ring-2 ring-primary/30 bg-primary/10"
                : "border-border",
            )}
          >
            <div className="text-xs uppercase tracking-wider text-muted-foreground">Starting</div>
            <div className="mt-1 text-xl font-semibold tabular-nums">{formatCurrency(p)}</div>
          </button>
        ))}
      </div>

      <div className="rounded-xl border bg-card/40 p-3 backdrop-blur-sm">
        <Label htmlFor="custom-balance" className="text-xs uppercase tracking-wider text-muted-foreground">
          Custom amount (USD)
        </Label>
        <Input
          id="custom-balance"
          type="number"
          inputMode="decimal"
          min={1}
          max={1_000_000}
          step={1}
          placeholder="e.g. 2500"
          value={custom}
          onChange={(e) => {
            setCustom(e.target.value);
            const n = Number(e.target.value);
            if (Number.isFinite(n) && n > 0) setValue(n);
          }}
          className="mt-1.5 bg-background/60"
        />
      </div>

      <div className="flex items-center justify-between rounded-xl border bg-card/40 p-3 backdrop-blur-sm">
        <div className="space-y-0.5">
          <div className="text-xs uppercase tracking-wider text-muted-foreground">You will start with</div>
          <div className="text-2xl font-semibold tabular-nums">{formatCurrency(value)}</div>
        </div>
        <Button
          onClick={() => onConfirm(value)}
          disabled={busy || !(value > 0)}
        >
          {busy ? "Working…" : ctaLabel}
        </Button>
      </div>
    </div>
  );
}
