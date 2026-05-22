"use client";

import {
  Button,
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from "@ta/ui";
import { Pause, Play, RefreshCw, XCircle } from "lucide-react";
import { useState } from "react";

import type { PaperAccount } from "@/lib/hooks/queries/use-paper-account";
import { usePaperAccountMutations } from "@/lib/hooks/mutations/use-paper-account-mutations";

import { StartingBalancePicker } from "./starting-balance-picker";

interface Props {
  account: PaperAccount;
}

export function AccountControls({ account }: Props) {
  const { start, pause, reset, closeOpen } = usePaperAccountMutations();
  const [resetOpen, setResetOpen] = useState(false);
  const status = account.status === "active" || account.status === "paused" || account.status === "inactive"
    ? account.status
    : "inactive";

  return (
    <div className="flex flex-wrap items-center gap-2">
      {status === "active" ? (
        <Button
          variant="secondary"
          onClick={() => pause.mutate()}
          disabled={pause.isPending}
        >
          <Pause className="mr-2 h-4 w-4" />
          {pause.isPending ? "Pausing…" : "Pause autonomous"}
        </Button>
      ) : (
        <Button
          onClick={() => start.mutate()}
          disabled={start.isPending || Number(account.balance) <= 0}
        >
          <Play className="mr-2 h-4 w-4" />
          {start.isPending ? "Starting…" : "Start autonomous"}
        </Button>
      )}

      <Button
        variant="outline"
        onClick={() => closeOpen.mutate()}
        disabled={closeOpen.isPending}
      >
        <XCircle className="mr-2 h-4 w-4" />
        {closeOpen.isPending ? "Closing..." : "Close open positions"}
      </Button>

      <Dialog open={resetOpen} onOpenChange={setResetOpen}>
        <DialogTrigger asChild>
          <Button variant="outline">
            <RefreshCw className="mr-2 h-4 w-4" />
            Reset
          </Button>
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reset paper trading</DialogTitle>
            <DialogDescription>
              Clears paper-mode signals, decisions, trades, lifecycle events and
              account events. Your bots, exchange connections and account stay
              intact. Pick a starting balance to begin again.
            </DialogDescription>
          </DialogHeader>

          <StartingBalancePicker
            defaultValue={Number.isFinite(Number(account.starting_balance)) ? Number(account.starting_balance) : 1000}
            ctaLabel="Reset and re-fund"
            busy={reset.isPending}
            onConfirm={(amt) =>
              reset.mutate(amt, {
                onSuccess: () => setResetOpen(false),
              })
            }
          />

          <DialogFooter className="text-xs text-muted-foreground">
            This action only affects paper-mode data. Live trading is unaffected.
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
