// [EF-KEY-03] exchange-health-check
//
// Performs a lightweight live connectivity check for an exchange account.
// Decrypts the API key in function memory, calls the exchange, then discards
// the plaintext. Stores only the health status result.
//
// Security: the decrypted key is never logged, never returned in the response,
// and is not retained after the function invocation ends.

import { getAuthenticatedUser, getUserProfile } from "../_shared/auth.ts"
import { writeAuditLog, writeSecurityLog } from "../_shared/audit.ts"
import { handleCors } from "../_shared/cors.ts"
import { Errors } from "../_shared/errors.ts"
import { getExchangeAdapter } from "../_shared/exchange/index.ts"
import { decrypt, fromStorageBase64 } from "../_shared/encryption.ts"
import { jsonResponse, withErrorHandler } from "../_shared/response.ts"
import {
  createSupabaseServiceClient,
  createSupabaseUserClient,
} from "../_shared/supabase.ts"
import { getRequestMeta } from "../_shared/types.ts"
import {
  ExchangeHealthCheckSchema,
  validateRequestBody,
} from "../_shared/validation.ts"
import { assertUserOwnsExchangeAccount } from "../_shared/ownership.ts"

Deno.serve((req: Request) =>
  withErrorHandler(req, async () => {
    const preflight = handleCors(req)
    if (preflight) return preflight

    if (req.method !== "POST") throw Errors.badRequest("Method not allowed")

    const { ipAddress, userAgent } = getRequestMeta(req)

    // ── 1. Auth + ownership ───────────────────────────────────────────────────
    const userClient = createSupabaseUserClient(req)
    const serviceClient = createSupabaseServiceClient()

    const user = await getAuthenticatedUser(userClient)
    const profile = await getUserProfile(serviceClient, user.id)

    const input = await validateRequestBody(req, ExchangeHealthCheckSchema)

    const account = await assertUserOwnsExchangeAccount(
      serviceClient,
      user.id,
      input.exchange_account_id,
    )

    // ── 2. Fetch encrypted key payload ────────────────────────────────────────
    const { data: keyRecord, error: keyError } = await serviceClient
      .from("encrypted_api_keys")
      .select("encrypted_api_key, encrypted_secret, encrypted_passphrase, key_status")
      .eq("exchange_account_id", account.id)
      .eq("key_status", "active")
      .single()

    if (keyError || !keyRecord) {
      throw Errors.notFound(
        "No active API key found for this exchange account. " +
        "Add or rotate the key before running a health check.",
      )
    }

    // ── 3. Decrypt in function memory ─────────────────────────────────────────
    // Plaintext exists only here; it is discarded when the scope ends.
    let apiKey: string
    let apiSecret: string
    let passphrase: string | undefined

    try {
      apiKey = await decrypt(fromStorageBase64(keyRecord.encrypted_api_key))
      apiSecret = await decrypt(fromStorageBase64(keyRecord.encrypted_secret))
      passphrase = keyRecord.encrypted_passphrase
        ? await decrypt(fromStorageBase64(keyRecord.encrypted_passphrase))
        : undefined
    } catch {
      throw Errors.internal(
        "Failed to decrypt API key. The key may have been corrupted or the encryption secret has changed.",
      )
    }

    // ── 4. Perform health check via exchange adapter ──────────────────────────
    const adapter = getExchangeAdapter(account.exchange_name)
    const now = new Date().toISOString()

    const healthResult = await adapter.healthCheck(
      apiKey,
      apiSecret,
      passphrase,
      account.testnet,
    )

    // Explicit zero-out intent (V8 may not honor this but communicates contract).
    apiKey = ""
    apiSecret = ""
    passphrase = ""

    // ── 5. Re-check for unexpected permission creep ───────────────────────────
    if (healthResult.permissions?.canWithdraw) {
      await Promise.all([
        serviceClient.from("exchange_accounts").update({
          withdrawal_detected: true,
          connection_status: "suspended",
          is_active: false,
          deactivated_at: now,
          deactivated_reason: "Withdrawal permission detected during health check",
        }).eq("id", account.id),
        writeSecurityLog(serviceClient, {
          userId: user.id,
          eventType: "withdrawal_detected_on_health_check",
          severity: "critical",
          ipAddress,
          userAgent,
          message:
            `CRITICAL: Withdrawal permission detected during health check for ${account.exchange_name} '${account.account_label}'. Account suspended.`,
          metadata: { exchange_account_id: account.id },
        }),
      ])

      throw Errors.forbidden(
        "CRITICAL: Withdrawal permission was detected on this API key during the health check. " +
        "The account has been suspended and linked bots paused. " +
        "Revoke this key on the exchange immediately.",
      )
    }

    // ── 6. Update health status in exchange_accounts ──────────────────────────
    const connectionStatus = healthResult.connected ? "connected" : "error"

    await serviceClient.from("exchange_accounts").update({
      last_health_check_at: now,
      last_health_status: connectionStatus,
      health_error_message: healthResult.error ?? null,
      connection_status: connectionStatus,
      can_read: healthResult.permissions?.canRead ?? account.can_read,
      can_trade: healthResult.permissions?.canTrade ?? account.can_trade,
    }).eq("id", account.id)

    // ── 7. Log if unhealthy ───────────────────────────────────────────────────
    if (!healthResult.connected) {
      await writeSecurityLog(serviceClient, {
        userId: user.id,
        eventType: "exchange_health_check_failed",
        severity: "medium",
        ipAddress,
        userAgent,
        message: `Exchange health check failed for ${account.exchange_name} '${account.account_label}': ${healthResult.error}`,
        metadata: { exchange_account_id: account.id },
      })
    }

    await writeAuditLog(serviceClient, {
      userId: user.id,
      actorRole: profile.role,
      action: "EXCHANGE_HEALTH_CHECK",
      tableName: "exchange_accounts",
      recordId: account.id,
      ipAddress,
      userAgent,
      newValues: {
        connected: healthResult.connected,
        latency_ms: healthResult.latencyMs,
        connection_status: connectionStatus,
      },
    })

    // ── 8. Return safe status — no key material ───────────────────────────────
    return jsonResponse(req, {
      exchange_account_id: account.id,
      exchange_name: account.exchange_name,
      account_label: account.account_label,
      connected: healthResult.connected,
      connection_status: connectionStatus,
      latency_ms: healthResult.latencyMs,
      server_time_offset_ms: healthResult.serverTimeOffsetMs,
      last_health_check_at: now,
      error: healthResult.error ?? null,
    })
  }),
)
