import type { MarketMove } from "../types";

export type MarketBook = {
  askPrice: number;
  askQty: number;
  bidPrice: number;
  bidQty: number;
};

export type MarketCandle = {
  close: number;
  high: number;
  low: number;
  open: number;
  time: number;
};

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

      const row = (await response.json()) as { priceChangePercent?: string; lastPrice?: string };

      return {
        symbol,
        change24h: Number(row.priceChangePercent ?? 0),
        lastPrice: Number(row.lastPrice ?? 0),
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

export async function fetchBookTicker(symbol: string): Promise<MarketBook | null> {
  const normalized = normalizeMarketSymbol(symbol);
  const response = await fetch(`https://api.binance.com/api/v3/ticker/bookTicker?symbol=${normalized}`);

  if (!response.ok) return null;

  const row = (await response.json()) as {
    askPrice?: string;
    askQty?: string;
    bidPrice?: string;
    bidQty?: string;
  };

  return {
    askPrice: Number(row.askPrice ?? 0),
    askQty: Number(row.askQty ?? 0),
    bidPrice: Number(row.bidPrice ?? 0),
    bidQty: Number(row.bidQty ?? 0),
  };
}

export async function fetchCandles(symbol: string): Promise<MarketCandle[]> {
  const normalized = normalizeMarketSymbol(symbol);
  const response = await fetch(`https://api.binance.com/api/v3/klines?symbol=${normalized}&interval=1m&limit=40`);

  if (!response.ok) return [];

  const rows = (await response.json()) as unknown[][];
  return rows.map((row) => ({
    time: Number(row[0] ?? 0),
    open: Number(row[1] ?? 0),
    high: Number(row[2] ?? 0),
    low: Number(row[3] ?? 0),
    close: Number(row[4] ?? 0),
  })).filter((row) => Number.isFinite(row.close) && row.close > 0);
}
