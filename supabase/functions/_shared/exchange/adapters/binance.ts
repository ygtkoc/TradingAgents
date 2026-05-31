import type {
  ExchangeAdapter,
  ExchangeHealthStatus,
  ExchangePermissions,
} from "../types.ts"

type BinanceAccountResponse = {
  canTrade?: boolean
  canWithdraw?: boolean
  canDeposit?: boolean
  accountType?: string
  permissions?: string[]
}

const PROD_BASE_URL = "https://api.binance.com"
const TESTNET_BASE_URL = "https://testnet.binance.vision"

export class BinanceAdapter implements ExchangeAdapter {
  readonly exchangeName = "binance"

  async checkPermissions(
    apiKey: string,
    apiSecret: string,
    _passphrase?: string,
    testnet = false,
  ): Promise<ExchangePermissions> {
    const account = await this.signedRequest<BinanceAccountResponse>(
      "/api/v3/account",
      apiKey,
      apiSecret,
      testnet,
    )

    const rawPermissions = [
      account.accountType,
      ...(account.permissions ?? []),
      account.canDeposit ? "deposit" : null,
      account.canTrade ? "trade" : null,
      account.canWithdraw ? "withdraw" : null,
    ].filter((item): item is string => !!item)

    return {
      canRead: true,
      canTrade: account.canTrade === true,
      canWithdraw: account.canWithdraw === true,
      accountType: account.accountType ?? "spot",
      rawPermissions,
    }
  }

  async healthCheck(
    apiKey: string,
    apiSecret: string,
    passphrase?: string,
    testnet = false,
  ): Promise<ExchangeHealthStatus> {
    const startedAt = Date.now()
    try {
      const serverTime = await this.publicRequest<{ serverTime: number }>("/api/v3/time", testnet)
      const permissions = await this.checkPermissions(apiKey, apiSecret, passphrase, testnet)
      return {
        connected: true,
        latencyMs: Date.now() - startedAt,
        serverTimeOffsetMs: serverTime.serverTime - Date.now(),
        permissions,
      }
    } catch (err) {
      return {
        connected: false,
        latencyMs: Date.now() - startedAt,
        error: err instanceof Error ? err.message : "Unknown Binance health error",
      }
    }
  }

  private async publicRequest<T>(path: string, testnet: boolean): Promise<T> {
    const response = await fetch(`${baseUrl(testnet)}${path}`)
    return await parseResponse<T>(response)
  }

  private async signedRequest<T>(
    path: string,
    apiKey: string,
    apiSecret: string,
    testnet: boolean,
  ): Promise<T> {
    const params = new URLSearchParams({
      recvWindow: "5000",
      timestamp: String(Date.now()),
    })
    const signature = await hmacSha256Hex(apiSecret, params.toString())
    params.set("signature", signature)

    const response = await fetch(`${baseUrl(testnet)}${path}?${params.toString()}`, {
      headers: { "X-MBX-APIKEY": apiKey },
    })
    return await parseResponse<T>(response)
  }
}

function baseUrl(testnet: boolean) {
  return testnet ? TESTNET_BASE_URL : PROD_BASE_URL
}

async function hmacSha256Hex(secret: string, payload: string) {
  const enc = new TextEncoder()
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  )
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(payload))
  return [...new Uint8Array(sig)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("")
}

async function parseResponse<T>(response: Response): Promise<T> {
  const text = await response.text()
  let body: unknown = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = text
  }

  if (!response.ok) {
    const message =
      body && typeof body === "object" && "msg" in body
        ? String((body as { msg?: unknown }).msg)
        : `Binance request failed with HTTP ${response.status}`
    throw new Error(message)
  }

  return body as T
}
