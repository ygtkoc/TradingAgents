// Mock exchange adapter — used during development and testing.
// Replace with a real adapter before connecting live exchange accounts.
//
// TODO(exchange-adapters): Create adapters/binance.ts, adapters/bybit.ts, etc.
//   Each adapter should:
//     1. Call the exchange's account-info or API-key-permission endpoint.
//     2. Map the response to ExchangePermissions.
//     3. NEVER place orders — read-only calls only.
//     4. Respect testnet flag (use separate base URL for testnet).
//     5. Handle exchange-specific error codes gracefully.
//     6. Complete within 8 seconds (Edge Function has a 10s soft limit).

import type {
  ExchangeAdapter,
  ExchangeHealthStatus,
  ExchangePermissions,
} from "./types.ts"

export class MockExchangeAdapter implements ExchangeAdapter {
  readonly exchangeName: string

  constructor(exchangeName: string) {
    this.exchangeName = exchangeName
  }

  async checkPermissions(
    _apiKey: string,
    _apiSecret: string,
    _passphrase?: string,
    testnet = false,
  ): Promise<ExchangePermissions> {
    // TODO: Replace with real exchange API call.
    // Example for Binance:
    //   GET /sapi/v1/account/apiRestrictions
    //   Requires signed request with timestamp + signature.
    //   Check enableWithdrawals, enableTrading, enableReading.

    console.warn(
      `[MockAdapter:${this.exchangeName}] checkPermissions called — testnet=${testnet}. ` +
      "This is a mock. Real exchange permission check not implemented yet.",
    )

    // Simulate a safe (non-withdrawal) trading key.
    await Promise.resolve()
    return {
      canRead: true,
      canTrade: true,
      canWithdraw: false, // Must be false; real adapter must check this
      canTransfer: false,
      ipRestricted: false,
      accountType: "spot",
      rawPermissions: ["SPOT", "FUTURES_READ"],
    }
  }

  async healthCheck(
    _apiKey: string,
    _apiSecret: string,
    _passphrase?: string,
    testnet = false,
  ): Promise<ExchangeHealthStatus> {
    // TODO: Replace with real exchange API call.
    // Example: GET /api/v3/time (Binance) — no auth required, measures latency.
    //          Then GET /api/v3/account for permission re-validation.

    console.warn(
      `[MockAdapter:${this.exchangeName}] healthCheck called — testnet=${testnet}. ` +
      "This is a mock.",
    )

    await Promise.resolve()
    return {
      connected: true,
      latencyMs: 42,
      serverTimeOffsetMs: 0,
      permissions: {
        canRead: true,
        canTrade: true,
        canWithdraw: false,
        ipRestricted: false,
      },
    }
  }
}
