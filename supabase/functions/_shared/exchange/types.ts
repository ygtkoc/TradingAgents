// Exchange adapter interface — implemented per-exchange in exchange/adapters/.
// The Edge Functions depend only on this interface; concrete adapters are
// injected at runtime via getExchangeAdapter().

export interface ExchangePermissions {
  canRead: boolean
  canTrade: boolean
  canWithdraw: boolean
  canTransfer?: boolean     // Some exchanges have separate transfer permission
  ipRestricted?: boolean    // Whether the key is IP-whitelist restricted
  accountType?: string      // 'spot', 'futures', 'unified'
  rawPermissions?: string[] // Raw permission strings from the exchange
}

export interface ExchangeHealthStatus {
  connected: boolean
  latencyMs?: number
  serverTimeOffsetMs?: number // Useful for detecting clock-skew issues
  permissions?: ExchangePermissions
  error?: string
}

export interface ExchangeAdapter {
  readonly exchangeName: string

  // Performs a lightweight authenticated call to the exchange to determine
  // what permissions the API key holds. Must NOT place any orders.
  // MUST complete within ~10 seconds for Edge Function timeout safety.
  checkPermissions(
    apiKey: string,
    apiSecret: string,
    passphrase?: string,
    testnet?: boolean,
  ): Promise<ExchangePermissions>

  // Performs a lightweight ping / server-time call using the API key.
  // Updates exchange_accounts.last_health_check_at/status/error.
  // Decrypts the API key payload inside the Edge Function, uses it for the
  // call, then discards plaintext from memory.
  healthCheck(
    apiKey: string,
    apiSecret: string,
    passphrase?: string,
    testnet?: boolean,
  ): Promise<ExchangeHealthStatus>
}
