"use client";

import { useQuery } from "@tanstack/react-query";

const BINANCE_EXCHANGE_INFO_URL = "https://api.binance.com/api/v3/exchangeInfo";

const FALLBACK_SYMBOLS: BinanceSymbol[] = [
  { binance: "BTCUSDT", internal: "BTC/USDT", base: "BTC" },
  { binance: "ETHUSDT", internal: "ETH/USDT", base: "ETH" },
  { binance: "SOLUSDT", internal: "SOL/USDT", base: "SOL" },
];

export interface BinanceSymbol {
  binance:  string;       // "BTCUSDT"
  internal: string;       // "BTC/USDT"
  base:     string;       // "BTC"
}

interface BinanceExchangeInfoResponse {
  symbols: Array<{
    symbol:      string;
    status:      string;
    baseAsset:   string;
    quoteAsset:  string;
    permissions?: string[];
  }>;
}

/**
 * Fetches every USDT spot pair Binance lists as TRADING. Falls back to a
 * tiny static list when the public API is unreachable so /bots/new still
 * loads — never blocks the page.
 *
 * Cached for 24 hours via React Query (the symbol set is very stable).
 */
export function useBinanceSymbols() {
  return useQuery<BinanceSymbol[]>({
    queryKey: ["binance-symbols", "spot-usdt"],
    staleTime: 24 * 60 * 60 * 1000,   // 24h
    gcTime:    7  * 24 * 60 * 60 * 1000,
    retry:     1,
    queryFn: async () => {
      try {
        const res = await fetch(BINANCE_EXCHANGE_INFO_URL, { cache: "force-cache" });
        if (!res.ok) throw new Error(`Binance ${res.status}`);
        const data = (await res.json()) as BinanceExchangeInfoResponse;
        const out: BinanceSymbol[] = [];
        for (const s of data.symbols ?? []) {
          if (s.status !== "TRADING")        continue;
          if (s.quoteAsset !== "USDT")       continue;
          // Skip Binance leveraged tokens (BULL/BEAR/UP/DOWN) — they confuse
          // beginners and aren't supported by our paper executor.
          if (/(UP|DOWN|BULL|BEAR)$/.test(s.baseAsset)) continue;
          out.push({
            binance:  s.symbol,
            internal: `${s.baseAsset}/USDT`,
            base:     s.baseAsset,
          });
        }
        out.sort((a, b) => a.base.localeCompare(b.base));
        if (out.length === 0) return FALLBACK_SYMBOLS;
        return out;
      } catch (err) {
        console.warn("binance.symbols.fetch_failed", { error: (err as Error).message });
        return FALLBACK_SYMBOLS;
      }
    },
  });
}
