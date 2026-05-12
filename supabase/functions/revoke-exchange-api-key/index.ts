// [EF-KEY-02] revoke-exchange-api-key
//
// Marks an exchange API key as revoked and deactivates the exchange account.
// The encrypted payload is NOT deleted — it is retained for audit purposes
// with key_status = 'revoked'.
//
// IMPORTANT: This function does not call the exchange to actually invalidate
// the key on their side — that is the user's responsibility. It only marks
// the key as revoked in our system and stops all bots using that account.

import { getAuthenticatedUser, getUserProfile } from "../_shared/auth.ts"
import { writeAuditLog, writeSecurityLog } from "../_shared/audit.ts"
import { handleCors } from "../_shared/cors.ts"
import { Errors } from "../_shared/errors.ts"
import { jsonResponse, withErrorHandler } from "../_shared/response.ts"
import {
  createSupabaseServiceClient,
  createSupabaseUserClient,
} from "../_shared/supabase.ts"
import { getRequestMeta } from "../_shared/types.ts"
import {
  RevokeExchangeApiKeySchema,
  validateRequestBody,
} from "../_shared/validation.ts"
import { assertUserOwnsExchangeAccount } from "../_shared/ownership.ts"

Deno.serve((req: Request) =>
  withErrorHandler(req, async () => {
    const preflight = handleCors(req)
    if (preflight) return preflight

    if (req.method !== "POST") throw Errors.badRequest("Method not allowed")

    const { ipAddress, userAgent } = getRequestMeta(req)

    // ── 1. Auth ──────────────────────────────────────────────────────────────
    const userClient = createSupabaseUserClient(req)
    const serviceClient = createSupabaseServiceClient()

    const user = await getAuthenticatedUser(userClient)
    const profile = await getUserProfile(serviceClient, user.id)

    // ── 2. Validate + ownership check ────────────────────────────────────────
    const input = await validateRequestBody(req, RevokeExchangeApiKeySchema)

    const account = await assertUserOwnsExchangeAccount(
      serviceClient,
      user.id,
      input.exchange_account_id,
    )

    // ── 3. Find and revoke the active key record ──────────────────────────────
    const { data: keyRecord, error: keyFetchError } = await serviceClient
      .from("encrypted_api_keys")
      .select("id, key_status")
      .eq("exchange_account_id", account.id)
      .in("key_status", ["active", "rotated"]) // Only revoke active/rotated keys
      .single()

    if (keyFetchError || !keyRecord) {
      throw Errors.notFound(
        "No active API key found for this exchange account",
      )
    }

    if (keyRecord.key_status === "revoked") {
      throw Errors.conflict("This API key is already revoked")
    }

    const now = new Date().toISOString()

    // ── 4. Service_role writes ────────────────────────────────────────────────

    // Mark key as revoked — encrypted payload retained for audit compliance.
    const { error: keyRevokeError } = await serviceClient
      .from("encrypted_api_keys")
      .update({
        key_status: "revoked",
        revoked_at: now,
        revoked_by: user.id,
        revoke_reason: input.reason ?? "User-initiated revocation",
      })
      .eq("id", keyRecord.id)

    if (keyRevokeError) throw Errors.internal("Failed to revoke API key")

    // Deactivate the exchange account so no bots can use it.
    const { error: accountError } = await serviceClient
      .from("exchange_accounts")
      .update({
        connection_status: "disconnected",
        is_active: false,
        deactivated_at: now,
        deactivated_reason: input.reason ?? "API key revoked by user",
      })
      .eq("id", account.id)
      .eq("user_id", user.id)

    if (accountError) throw Errors.internal("Failed to deactivate exchange account")

    // Pause all active bots linked to this exchange account so they don't
    // attempt to place orders with a revoked key.
    const { error: botPauseError } = await serviceClient
      .from("bots")
      .update({ status: "paused" })
      .eq("exchange_account_id", account.id)
      .eq("user_id", user.id)
      .in("status", ["active"])

    if (botPauseError) {
      // Non-fatal: log but don't fail the revocation.
      console.error("[REVOKE KEY] Failed to pause linked bots:", botPauseError)
    }

    // ── 5. Audit + security logs ──────────────────────────────────────────────
    await Promise.all([
      writeSecurityLog(serviceClient, {
        userId: user.id,
        eventType: "api_key_revoked",
        severity: "info",
        ipAddress,
        userAgent,
        message: `API key revoked for exchange account '${account.account_label}' (${account.exchange_name})`,
        metadata: {
          exchange_account_id: account.id,
          exchange_name: account.exchange_name,
          reason: input.reason,
        },
      }),
      writeAuditLog(serviceClient, {
        userId: user.id,
        actorRole: profile.role,
        action: "API_KEY_REVOKED",
        tableName: "encrypted_api_keys",
        recordId: keyRecord.id,
        ipAddress,
        userAgent,
        newValues: {
          key_status: "revoked",
          revoke_reason: input.reason,
        },
      }),
    ])

    return jsonResponse(req, {
      exchange_account_id: account.id,
      exchange_name: account.exchange_name,
      account_label: account.account_label,
      revoked_at: now,
      message:
        "API key revoked. All linked bots have been paused. " +
        "Remember to also invalidate the key on the exchange.",
    })
  }),
)
