"use client";

import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@ta/ui";
import { formatCurrency } from "@ta/utils";
import { CheckCircle2, Loader2, Sparkles, ShieldAlert } from "lucide-react";
import { useState } from "react";

import { usePaperAccountMutations } from "@/lib/hooks/mutations/use-paper-account-mutations";
import { StartingBalancePicker } from "./starting-balance-picker";

/**
 * Paper-trading onboarding card. Replaces the bare picker with explicit
 * status banners so the user sees:
 *
 *   • the chosen amount before they submit
 *   • a loading state while the EF runs
 *   • a clear success banner with the actual balance the EF returned
 *   • a clear error banner with the exact message (incl. "function not
 *     deployed" hints from the wrapper)
 */
export function PaperOnboardingCard() {
  const { create } = usePaperAccountMutations();
  const [chosen, setChosen] = useState<number | null>(null);

  const onConfirm = (amount: number) => {
    setChosen(amount);
    create.mutate(amount);
  };

  const errMsg = create.isError ? (create.error as Error)?.message ?? "Unknown error" : null;
  const data   = create.data;

  return (
    <Card className="relative overflow-hidden border-border/50 bg-gradient-to-br from-card to-card/40 backdrop-blur-sm">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_right,hsl(var(--primary)/0.12),transparent_55%)]" />
      <CardHeader className="relative">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-primary" />
          <CardTitle>Start a paper-trading simulation</CardTitle>
        </div>
        <CardDescription>
          Pick a starting balance. The autonomous engine creates signals,
          runs agent decisions, and simulates trades on real Binance prices.
        </CardDescription>
      </CardHeader>
      <CardContent className="relative space-y-4">
        <StartingBalancePicker
          defaultValue={1000}
          ctaLabel={create.isPending ? "Creating account…" : "Create paper account"}
          busy={create.isPending}
          onConfirm={onConfirm}
        />

        {create.isPending ? (
          <div className="flex items-center gap-2 rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-xs">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
            <span>
              Funding paper account with <strong>{formatCurrency(chosen ?? 0)}</strong>…
            </span>
          </div>
        ) : null}

        {data && !create.isPending ? (
          <div className="flex items-start gap-2 rounded-md border border-success/30 bg-success/5 px-3 py-2 text-xs">
            <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" />
            <div>
              <div className="font-medium">Paper account ready</div>
              <div className="text-muted-foreground">
                Status: <strong>{data.status}</strong> · Balance:{" "}
                <strong>{formatCurrency(Number(data.balance))}</strong>
              </div>
            </div>
          </div>
        ) : null}

        {errMsg ? (
          <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-xs">
            <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" />
            <div className="space-y-1">
              <div className="font-medium">Could not create paper account</div>
              <pre className="whitespace-pre-wrap break-words text-[11px] leading-relaxed">
                {errMsg}
              </pre>
              <Button
                size="sm" variant="outline" className="h-7"
                onClick={() => create.reset()}
              >
                Dismiss
              </Button>
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
