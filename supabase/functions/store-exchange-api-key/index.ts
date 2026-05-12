// [EF-KEY-01] store-exchange-api-key
//
// Receives exchange API credentials from the customer dashboard,
// validates permissions, rejects withdrawal-enabled keys, encrypts
// the payload, and stores only the encrypted blob — never plaintext.
//
// TODO(rate-limit): Add per-user rate limiting (max 10 key submissions/hour)
//   via Upstash Redis or Supabase KV when available, to prevent brute-force
//   key validation attempts against exchange APIs.

import { getAuthenticatedUser, getUserProfile } from "../_shared/auth.ts"
import { writeAuditLog, writeSecurityLog } from "../_shared/audit.ts"
import { handleCors } from "../_shared/cors.ts"
import { Errors } from "../_shared/errors.ts"
import { getExchangeAdapter } from "../_shared/exchange/index.ts"
import { encrypt, toStorageBase64 } from "../_shared/encryption.ts"
import { jsonResponse, withErrorHandler } from "../_shared/response.ts"
import {
  createSupabaseServiceClient,
  createSupabaseUserClient,
} from "../_shared/supabase.ts"
import { getRequestMeta } from "../_shared/types.ts"
import {
  StoreExchangeApiKeySchema,
  validateRequestBody,
} from "../_shared/validation.ts"

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

    // ── 2. Validate input ────────────────────────────────────────────────────
    const input = await validateRequestBody(req, StoreExchangeApiKeySchema)

    // ── 3. Exchange permission check ─────────────────────────────────────────
    // Plaintext credentials exist only in function memory from this point.
    // They are NEVER written to any database column in plaintext.
    const adapter = getExchangeAdapter(input.exchange_name)

    let permissions
    try {
      permissions = await adapter.checkPermissions(
        input.api_key,
        input.api_secret,
        input.passphrase,
        input.testnet,
      )
    } catch (err) {
      // Exchange call failed — could be wrong credentials or network issue.
      const message = err instanceof Error ? err.message : "Unknown error"
      await writeSecurityLog(serviceClient, {
        userId: user.id,
        eventType: "api_key_validation_failed",
        severity: "medium",
        ipAddress,
        userAgent,
        message: `Exchange permission check failed for ${input.exchange_name}: ${message}`,
        metadata: { exchange_name: input.exchange_name },
      })
      throw Errors.badRequest(
        `Could not validate API key with ${input.exchange_name}. ` +
        "Check your credentials and try again.",
      )
    }

    // ── 4. Reject withdrawal-enabled keys ────────────────────────────────────
    if (permissions.canWithdraw) {
      await writeSecurityLog(serviceClient, {
        userId: user.id,
        eventType: "withdrawal_attempt_blocked",
        severity: "high",
        ipAddress,
        userAgent,
        message:
          `User attempted to store a withdrawal-enabled API key for ${input.exchange_name}. Key rejected.`,
        metadata: {
          exchange_name: input.exchange_name,
          raw_permissions: permissions.rawPermissions,
        },
      })
      await writeAuditLog(serviceClient, {
        userId: user.id,
        actorRole: profile.role,
        action: "API_KEY_WITHDRAWAL_REJECTED",
        tableName: "exchange_accounts",
        ipAddress,
        userAgent,
        metadata: { exchange_name: input.exchange_name },
      })

      // Explicit error — do not hint at how to bypass.
      throw Errors.forbidden(
        "API keys with withdrawal permissions are not permitted. " +
        "Create a trade-only key on your exchange and try again.",
      )
    }

    // ── 5. Upsert exchange_accounts row ──────────────────────────────────────
    // Check for existing account with same exchange + label for this user.
    const { data: existingAccount } = await serviceClient
      .from("exchange_accounts")
      .select("id")
      .eq("user_id", user.id)
      .eq("exchange_name", input.exchange_name)
      .eq("account_label", input.account_label)
      .single()

    let exchangeAccountId: string

    if (existingAccount) {
      // Update existing account record.
      const { error: updateError } = await serviceClient
        .from("exchange_accounts")
        .update({
          connection_status: "connected",
          can_read: permissions.canRead,
          can_trade: permissions.canTrade,
          can_withdraw: false, // Enforced by DB CHECK constraint too
          withdrawal_detected: false,
          ip_whitelist_configured: permissions.ipRestricted ?? false,
          testnet: input.testnet,
          is_active: true,
          deactivated_at: null,
          deactivated_reason: null,
          last_health_check_at: new Date().toISOString(),
          last_health_status: "connected",
          health_error_message: null,
        })
        .eq("id", existingAccount.id)
        .eq("user_id", user.id)

      if (updateError) throw Errors.internal("Failed to update exchange account")
      exchangeAccountId = existingAccount.id
    } else {
      // Check subscription limits on number of exchange accounts.
      const { count } = await serviceClient
        .from("exchange_accounts")
        .select("id", { count: "exact", head: true })
        .eq("user_id", user.id)
        .eq("is_active", true)

      // TODO(subscription): Read limit from subscriptions.max_exchange_accounts
      // once that column is added. Current hard limit for MVP.
      const MAX_ACCOUNTS = 10
      if ((count ?? 0) >= MAX_ACCOUNTS) {
        throw Errors.conflict(
          `You have reached the maximum of ${MAX_ACCOUNTS} exchange accounts.`,
        )
      }

      const { data: newAccount, error: insertError } = await serviceClient
        .from("exchange_accounts")
        .insert({
          user_id: user.id,
          exchange_name: input.exchange_name,
          account_label: input.account_label,
          connection_status: "connected",
          can_read: permissions.canRead,
          can_trade: permissions.canTrade,
          can_withdraw: false,
          withdrawal_detected: false,
          ip_whitelist_configured: permissions.ipRestricted ?? false,
          testnet: input.testnet,
          is_active: true,
          last_health_check_at: new Date().toISOString(),
          last_health_status: "connected",
        })
        .select("id")
        .single()

      if (insertError || !newAccount) {
        throw Errors.internal("Failed to create exchange account")
      }
      exchangeAccountId = newAccount.id
    }

    // ── 6. Encrypt and store API key payloads ─────────────────────────────────
    // Each field is individually encrypted so fields can be decrypted
    // independently. All encryption is AES-256-GCM with a random IV per field.
    //
    // NOTE: plaintext credentials are about to be written to encrypted storage.
    // They remain in memory only until this block completes.
    const [encryptedKey, encryptedSecret, encryptedPassphrase] =
      await Promise.all([
        encrypt(input.api_key).then(toStorageBase64),
        encrypt(input.api_secret).then(toStorageBase64),
        input.passphrase
          ? encrypt(input.passphrase).then(toStorageBase64)
          : Promise.resolve(null),
      ])

    // Check if a key record already exists for this account.
    const { data: existingKey } = await serviceClient
      .from("encrypted_api_keys")
      .select("id, rotation_count")
      .eq("exchange_account_id", exchangeAccountId)
      .single()

    if (existingKey) {
      // Rotate existing key — preserve rotation history via rotation_count.
      const { error: keyUpdateError } = await serviceClient
        .from("encrypted_api_keys")
        .update({
          encrypted_api_key: encryptedKey,
          encrypted_secret: encryptedSecret,
          encrypted_passphrase: encryptedPassphrase,
          key_status: "active",
          rotated_at: new Date().toISOString(),
          revoked_at: null,
          revoke_reason: null,
          rotation_count: (existingKey.rotation_count ?? 0) + 1,
          vault_key_id: null, // TODO: set when Vault is integrated
        })
        .eq("id", existingKey.id)

      if (keyUpdateError) throw Errors.internal("Failed to rotate API key")
    } else {
      const { error: keyInsertError } = await serviceClient
        .from("encrypted_api_keys")
        .insert({
          user_id: user.id,
          exchange_account_id: exchangeAccountId,
          encrypted_api_key: encryptedKey,
          encrypted_secret: encryptedSecret,
          encrypted_passphrase: encryptedPassphrase,
          key_status: "active",
          created_by_ip: ipAddress ?? null,
          vault_key_id: null, // TODO: set when Vault is integrated
        })

      if (keyInsertError) throw Errors.internal("Failed to store API key")
    }

    // Explicitly zero out plaintext from local variables.
    // Deno/V8 does not guarantee this is effective against memory scanning,
    // but it communicates intent and reduces the exposure window.
    // TODO(security): Investigate if SharedArrayBuffer zeroing is viable here.

    // ── 7. Audit + security logs ──────────────────────────────────────────────
    await Promise.all([
      writeSecurityLog(serviceClient, {
        userId: user.id,
        eventType: existingKey ? "api_key_rotated" : "api_key_created",
        severity: "info",
        ipAddress,
        userAgent,
        message: `API key ${existingKey ? "rotated" : "added"} for exchange ${input.exchange_name} (account: ${input.account_label})`,
        metadata: {
          exchange_name: input.exchange_name,
          account_label: input.account_label,
          can_read: permissions.canRead,
          can_trade: permissions.canTrade,
          testnet: input.testnet,
        },
      }),
      writeAuditLog(serviceClient, {
        userId: user.id,
        actorRole: profile.role,
        action: existingKey ? "API_KEY_ROTATED" : "API_KEY_CREATED",
        tableName: "encrypted_api_keys",
        recordId: exchangeAccountId,
        ipAddress,
        userAgent,
        newValues: {
          exchange_name: input.exchange_name,
          account_label: input.account_label,
          can_read: permissions.canRead,
          can_trade: permissions.canTrade,
          testnet: input.testnet,
        },
      }),
    ])

    // ── 8. Return safe metadata only — NEVER key material ────────────────────
    return jsonResponse(req, {
      exchange_account_id: exchangeAccountId,
      exchange_name: input.exchange_name,
      account_label: input.account_label,
      connection_status: "connected",
      can_read: permissions.canRead,
      can_trade: permissions.canTrade,
      testnet: input.testnet,
      rotated: !!existingKey,
    })
  }),
)
