"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle, ErrorState, PageHeader, Skeleton } from "@ta/ui";
import { ShieldCheck } from "lucide-react";

import { ExchangeCard } from "@/components/exchange/exchange-card";
import { useExchangeConnections } from "@/lib/hooks/queries/use-exchange-connections";

const PROVIDERS = [
  { exchange: "binance" as const,  label: "Binance",  blurb: "Spot. Public BTC/ETH/SOL price feed used by paper trading." },
  { exchange: "bybit" as const,    label: "Bybit",    blurb: "USDT-perp. Live trading off by default." },
  { exchange: "coinbase" as const, label: "Coinbase", blurb: "Advanced Trade. Live trading off by default." },
];

export default function ExchangesPage() {
  const conns = useExchangeConnections();

  const byExchange = new Map((conns.data ?? []).map((c) => [c.exchange.toLowerCase(), c]));

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5">
      <PageHeader
        title="Exchange connections"
        description="Connect read+trade keys for live execution. Paper trading does not require any connection."
      />

      {/* ── Safety banner ───────────────────────────────────────────────────── */}
      <div className="flex items-start gap-4 rounded-2xl border border-success/20 bg-success/5 px-5 py-4 backdrop-blur-sm">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-success/20 bg-success/10">
          <ShieldCheck className="h-5 w-5 text-success" />
        </div>
        <div>
          <div className="text-[13px] font-semibold text-foreground">Your secrets are encrypted</div>
          <p className="mt-0.5 text-[12px] leading-relaxed text-muted-foreground">
            API secrets are encrypted with{" "}
            <code className="rounded bg-card/60 px-1 font-mono text-[11px]">API_KEY_ENCRYPTION_SECRET</code>{" "}
            server-side and never returned to the browser.
            Live trading remains disabled until you opt in per-connection.
          </p>
        </div>
      </div>

      {conns.isError ? (
        <ErrorState onRetry={() => void conns.refetch()} />
      ) : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {conns.isLoading
          ? Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-44 w-full rounded-2xl" />
            ))
          : PROVIDERS.map((p) => (
              <ExchangeCard
                key={p.exchange}
                exchange={p.exchange}
                label={p.label}
                blurb={p.blurb}
                connection={byExchange.get(p.exchange) ?? null}
              />
            ))}
      </div>
    </div>
  );
}
