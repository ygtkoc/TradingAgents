"use client";

import {
  Button,
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
  Input, Label,
} from "@ta/ui";
import { Loader2, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";

import { useExchangeMutations } from "@/lib/hooks/mutations/use-exchange-mutations";

interface Props {
  exchange: string;       // "binance" | "bybit" | "coinbase"
  label:    string;       // human label
  defaultLabel?: string;
}

export function ConnectExchangeDialog({ exchange, label, defaultLabel }: Props) {
  const { create } = useExchangeMutations();
  const [open, setOpen] = useState(false);
  const [name, setName]       = useState(defaultLabel ?? `${label} (main)`);
  const [apiKey, setApiKey]   = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [error, setError]     = useState<string | null>(null);

  const reset = () => {
    setApiKey("");
    setApiSecret("");
    setError(null);
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!apiKey || !apiSecret) {
      setError("Both API key and API secret are required.");
      return;
    }
    const res = await create.mutateAsync({
      exchange, label: name.trim() || `${label} connection`,
      api_key:    apiKey,
      api_secret: apiSecret,
    });
    if (!res.ok) {
      setError(res.error.message);
      return;
    }
    reset();
    setOpen(false);
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) reset(); }}>
      <DialogTrigger asChild>
        <Button size="sm">Connect</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Connect {label}</DialogTitle>
          <DialogDescription>
            Provide an API key with <strong>trade enabled</strong> and{" "}
            <strong>withdrawals disabled</strong>. The secret is encrypted server-side and is never
            returned to the browser after save.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="conn-label">Label</Label>
            <Input id="conn-label" value={name} onChange={(e) => setName(e.target.value)} maxLength={60} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="api-key">API key</Label>
            <Input
              id="api-key"
              type="text"
              autoComplete="off"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              required
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="api-secret">API secret</Label>
            <Input
              id="api-secret"
              type="password"
              autoComplete="off"
              value={apiSecret}
              onChange={(e) => setApiSecret(e.target.value)}
              required
            />
          </div>

          <div className="flex items-center gap-2 rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground">
            <ShieldCheck className="h-4 w-4 shrink-0 text-success" />
            <span>
              Live trading remains <strong>disabled</strong> until you explicitly enable it on the
              connection and pass the platform live-execution gates.
            </span>
          </div>

          {error ? (
            <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive-foreground">
              {error}
            </div>
          ) : null}

          <DialogFooter>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? (
                <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Saving…</>
              ) : (
                "Save connection"
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
