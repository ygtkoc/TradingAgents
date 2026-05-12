// Adapter factory — returns the correct ExchangeAdapter for a given exchange name.
// Add real adapters here as they are built.
//
// TODO(exchange-adapters): Import and register real adapters:
//   import { BinanceAdapter } from "./adapters/binance.ts"
//   import { BybitAdapter } from "./adapters/bybit.ts"
//   import { KrakenAdapter } from "./adapters/kraken.ts"

import type { ExchangeAdapter } from "./types.ts"
import { MockExchangeAdapter } from "./mock-adapter.ts"

export function getExchangeAdapter(exchangeName: string): ExchangeAdapter {
  const name = exchangeName.toLowerCase()

  switch (name) {
    // TODO: Uncomment when real adapters are implemented:
    // case "binance":
    //   return new BinanceAdapter()
    // case "bybit":
    //   return new BybitAdapter()
    // case "kraken":
    //   return new KrakenAdapter()
    // case "coinbase":
    //   return new CoinbaseAdapter()

    default:
      // Fall back to mock adapter for all unknown exchanges during development.
      // In production this should throw for unsupported exchanges.
      console.warn(
        `[ExchangeAdapterFactory] No real adapter for '${name}' — using mock. ` +
        "This must be replaced before production.",
      )
      return new MockExchangeAdapter(name)
  }
}

export type { ExchangeAdapter, ExchangeHealthStatus, ExchangePermissions } from "./types.ts"
