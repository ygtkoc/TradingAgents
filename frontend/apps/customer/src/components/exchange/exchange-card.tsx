"use client";

import { Badge, Button, Card, CardContent, CardHeader, CardTitle } from "@ta/ui";
import { cn } from "@ta/utils";
import { CheckCircle2, Link2, Link2Off, ShieldAlert, Trash2 } from "lucide-react";
import type { ExchangeAccountSafe } from "@ta/types";

import { useExchangeMutations } from "@/lib/hooks/mutations/use-exchange-mutations";
import { ConnectExchangeDialog } from "./connect-dialog";

interface Props {
  exchange: "binance" | "bybit" | "coinbase";
  label:    string;
  blurb:    string;
  connection?: ExchangeAccountSafe | null;
}

const EXCHANGE_COLORS: Record<string, string> = {
  binance:  "border-warning/20  bg-warning/5",
  bybit:    "border-primary/20  bg-primary/5",
  coinbase: "border-success/20  bg-success/5",
};

const EXCHANGE_GLOW: Record<string, string> = {
  binance:  "hsl(var(--warning)/0.08)",
  bybit:    "hsl(var(--primary)/0.08)",
  coinbase: "hsl(var(--success)/0.08)",
};

export function ExchangeCard({ exchange, label, blurb, connection }: Props) {
  const { test, remove } = useExchangeMutations();
  const isConnected = !!connection;
  const safe        = connection ? !connection.can_withdraw : true;

  return (
    <Card className={cn(
      "relative overflow-hidden transition-all duration-200",
      isConnected ? EXCHANGE_COLORS[exchange] : "border-border/50 bg-card/60",
    )}>
      {/* Radial glow */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background: `radial-gradient(circle at top right, ${EXCHANGE_GLOW[exchange] ?? "transparent"}, transparent 60%)`,
        }}
      />

      {/* Connection status stripe */}
      {isConnected && (
        <div className="absolute inset-x-0 top-0 h-[2px] bg-gradient-to-r from-transparent via-success/60 to-transparent" />
      )}

      <CardHeader className="relative pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            {/* Exchange icon bubble */}
            <div className={cn(
              "flex h-9 w-9 items-center justify-center rounded-xl border text-[13px] font-bold",
              isConnected
                ? "border-success/20 bg-success/10 text-success"
                : "border-border/40 bg-card/60 text-muted-foreground",
            )}>
              {isConnected
                ? <CheckCircle2 className="h-4 w-4" />
                : <Link2Off className="h-4 w-4" />}
            </div>
            <div>
              <CardTitle className="text-[14px] font-semibold">{label}</CardTitle>
              <p className="mt-0.5 text-[11px] text-muted-foreground/70">{blurb}</p>
            </div>
          </div>

          {isConnected ? (
            <Badge
              variant={safe ? "success" : "destructive"}
              className="shrink-0 gap-1 text-[10px]"
            >
              {safe
                ? (<><CheckCircle2 className="h-2.5 w-2.5" />live-ready</>)
                : (<><ShieldAlert className="h-2.5 w-2.5" />withdraw on</>)}
            </Badge>
          ) : null}
        </div>
      </CardHeader>

      <CardContent className="relative space-y-3">
        {isConnected ? (
          <>
            <div className="space-y-1.5 rounded-xl border border-border/30 bg-card/40 px-3 py-2.5 text-[12px]">
              {connection!.label ? (
                <div className="flex justify-between">
                  <span className="text-muted-foreground/60">Label</span>
                  <span className="font-medium text-foreground">{connection!.label}</span>
                </div>
              ) : null}
              <div className="flex justify-between">
                <span className="text-muted-foreground/60">Permissions</span>
                <div className="flex items-center gap-1">
                  {connection!.can_trade
                    ? <Badge variant="success" className="text-[9px]">trade</Badge>
                    : <Badge variant="secondary" className="text-[9px]">read-only</Badge>}
                  {connection!.can_withdraw
                    ? <Badge variant="destructive" className="text-[9px]">withdraw</Badge>
                    : <Badge variant="outline" className="text-[9px]">no-withdraw</Badge>}
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                className="flex-1 gap-1.5"
                disabled={test.isPending}
                onClick={() => test.mutate(connection!.id)}
              >
                <Link2 className="h-3.5 w-3.5" />
                Test connection
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="text-muted-foreground hover:text-destructive"
                disabled={remove.isPending}
                onClick={() => {
                  if (window.confirm(`Disconnect ${label}? Stored credentials will be revoked.`)) {
                    remove.mutate(connection!.id);
                  }
                }}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          </>
        ) : (
          <ConnectExchangeDialog exchange={exchange} label={label} />
        )}
      </CardContent>
    </Card>
  );
}
