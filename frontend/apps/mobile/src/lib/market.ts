import type { MarketMove } from "../types";

export function normalizeMarketSymbol(symbol: string) {
  const clean = symbol.replace(/[^a-zA-Z0-9]/g, "").toUpperCase();

  if (clean.endsWith("USDT")) {
    return clean;
  }

  if (clean.endsWith("USD")) {
    return `${clean.slice(0, -3)}USDT`;
  }

  return `${clean}USDT`;
}

export async function fetchMarketMoves(symbols: string[]) {
  const uniqueSymbols = Array.from(new Set(symbols.map(normalizeMarketSymbol))).slice(0, 8);
  const settled = await Promise.allSettled(
    uniqueSymbols.map(async (symbol): Promise<MarketMove> => {
      const response = await fetch(`https://api.binance.com/api/v3/ticker/24hr?symbol=${symbol}`);

      if (!response.ok) {
        throw new Error(`Ticker failed for ${symbol}`);
      }

      const row = (await response.json()) as { priceChangePercent?: string };

      return {
        symbol,
        change24h: Number(row.priceChangePercent ?? 0),
      };
    }),
  );

  return settled.reduce<Record<string, MarketMove>>((acc, item) => {
    if (item.status === "fulfilled") {
      acc[item.value.symbol] = item.value;
    }

    return acc;
  }, {});
}
