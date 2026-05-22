"use client";

import { cn } from "@ta/utils";
import { useQuery } from "@tanstack/react-query";
import { Activity, Wifi } from "lucide-react";

import { useBots } from "@/lib/hooks/queries/use-bots";
import { formatPrice } from "@/lib/format-price";

interface TickerPrice {
  symbol: string;
  price: number;
}

function normalizeSymbol(symbol: string): string {
  return symbol.replace("/", "").toUpperCase();
}

function displaySymbol(symbol: string): string {
  if (symbol.includes("/")) return symbol.toUpperCase();
  return symbol.replace(/(USDT|USD|BTC|ETH)$/u, "/$1").toUpperCase();
}

async function fetchBinancePrices(symbols: string[]): Promise<Map<string, TickerPrice>> {
  const normalized = Array.from(new Set(symbols.map(normalizeSymbol))).filter(Boolean);
  if (normalized.length === 0) return new Map();

  const url = `https://api.binance.com/api/v3/ticker/price?symbols=${encodeURIComponent(JSON.stringify(normalized))}`;
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`Binance ticker failed: ${response.status}`);

  const rows = (await response.json()) as Array<{ symbol: string; price: string }>;
  const prices = new Map<string, TickerPrice>();
  for (const row of rows) {
    const price = Number(row.price);
    if (Number.isFinite(price) && price > 0) {
      prices.set(row.symbol, { symbol: row.symbol, price });
    }
  }
  return prices;
}

export function PriceTicker() {
  const bots = useBots();
  const symbols = Array.from(new Set((bots.data ?? []).flatMap((bot) => bot.trading_pairs ?? []))).filter(Boolean);

  const prices = useQuery({
    queryKey: ["topbar-price-ticker", symbols.map(normalizeSymbol).sort().join("|")],
    enabled: symbols.length > 0,
    staleTime: 0,
    refetchInterval: 1_000,
    refetchIntervalInBackground: true,
    queryFn: () => fetchBinancePrices(symbols),
  });

  if (bots.isLoading) {
    return (
      <div className="flex h-9 items-center gap-2 border-t border-border/30 text-[11px] text-muted-foreground">
        <Activity className="h-3.5 w-3.5 animate-pulse" />
        Loading bot prices
      </div>
    );
  }

  if (symbols.length === 0) return null;

  const items = symbols.map((symbol) => {
    const normalized = normalizeSymbol(symbol);
    const price = prices.data?.get(normalized)?.price ?? null;
    return { symbol, normalized, price };
  });
  const renderTickerGroup = (groupId: string) => (
    <div className="flex shrink-0 items-center gap-4 px-5" aria-hidden={groupId !== "primary"}>
      <div className="flex items-center gap-1.5 pr-2 text-[10px] font-semibold uppercase text-muted-foreground/70">
        <Wifi className={cn("h-3 w-3", prices.isError ? "text-destructive" : "text-success")} />
        Live prices
      </div>

      {items.map((item) => (
        <div key={`${groupId}-${item.normalized}`} className="flex items-center gap-2 text-[12px]">
          <span className="font-mono font-semibold text-foreground">{displaySymbol(item.symbol)}</span>
          <span className="font-semibold tabular-nums text-success">
            {item.price != null ? formatPrice(item.price) : "-"}
          </span>
          <span className="h-1 w-1 rounded-full bg-border" />
        </div>
      ))}
    </div>
  );

  return (
    <div className="relative -mx-5 h-9 overflow-hidden border-t border-border/30 bg-card/35">
      <div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-10 bg-gradient-to-r from-background/90 to-transparent" />
      <div className="pointer-events-none absolute inset-y-0 right-0 z-10 w-10 bg-gradient-to-l from-background/90 to-transparent" />

      <div className="flex h-full w-max items-center whitespace-nowrap ticker-marquee">
        {renderTickerGroup("primary")}
        {renderTickerGroup("duplicate")}
      </div>
    </div>
  );
}
