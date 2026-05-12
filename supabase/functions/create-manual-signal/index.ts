// [EF-SIG-01] create-manual-signal
//
// User-initiated signal insertion — the ONLY path for a user to inject
// a signal into the pipeline.
//
// Security model:
//   - All writes go through service_role after server-side validation.
//   - The signal enters with status='pending' and signal_type='manual'.
//   - It MUST still flow through the full agent pipeline (analysis → risk →
//     security → execution). This endpoint triggers the pipeline's INPUT only.
//   - Users cannot set confidence, score, or status directly.
//   - Signal injection is gated by subscription plan and bot status.
//
// TODO(queue): Publish signal_id to PGMQ 'signal_received' queue so the
//   Python Agent Engine picks it up immediately without polling.

import {
  getAuthenticatedUser,
  getUserProfile,
  getUserSubscription,
} from "../_shared/auth.ts"
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
  CreateManualSignalSchema,
  validateRequestBody,
} from "../_shared/validation.ts"
import { assertUserOwnsBot } from "../_shared/ownership.ts"

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
    const input = await validateRequestBody(req, CreateManualSignalSchema)

    // ── 3. Ownership check ───────────────────────────────────────────────────
    const bot = await assertUserOwnsBot(serviceClient, user.id, input.bot_id)

    // ── 4. Bot status validation ─────────────────────────────────────────────
    if (bot.is_archived) {
      throw Errors.badRequest("Cannot send signals to an archived bot")
    }
    if (!["active", "paused"].includes(bot.status)) {
      throw Errors.badRequest(
        `Bot is in '${bot.status}' status. Start or unpause the bot before sending signals.`,
      )
    }

    // ── 5. Subscription + live trading gate ──────────────────────────────────
    const subscription = await getUserSubscription(serviceClient, user.id)

    // Live-mode bots require an active subscription with real trading enabled.
    if (bot.mode === "live") {
      if (!subscription || !subscription.real_trading_allowed) {
        throw Errors.forbidden(
          "Your current plan does not allow live trading. " +
          "Upgrade your subscription to enable live bots.",
        )
      }
      if (
        !["active", "trialing"].includes(subscription.status)
      ) {
        throw Errors.forbidden(
          "Your subscription is not active. Resolve your billing to continue live trading.",
        )
      }
    }

    // TODO(rate-limit): Gate on max_trades_per_day from subscription.
    // Count today's signals for this user and enforce the cap.

    // ── 6. Insert signal via service_role ─────────────────────────────────────
    const now = new Date().toISOString()

    const { data: signal, error: signalError } = await serviceClient
      .from("signals")
      .insert({
        user_id: user.id,
        bot_id: input.bot_id,
        exchange: input.exchange,
        symbol: input.symbol,
        direction: input.direction,
        signal_type: "manual", // Always 'manual' for user-initiated signals
        confidence: null,      // Set by agent pipeline — user cannot set this
        score: null,
        status: "pending",
        metadata: {
          ...input.metadata,
          created_from: "manual_signal_endpoint",
        },
      })
      .select("id, created_at")
      .single()

    if (signalError || !signal) {
      throw Errors.internal("Failed to create signal")
    }

    // ── 7. Audit log ─────────────────────────────────────────────────────────
    await writeAuditLog(serviceClient, {
      userId: user.id,
      actorRole: profile.role,
      action: "MANUAL_SIGNAL_CREATED",
      tableName: "signals",
      recordId: signal.id,
      ipAddress,
      userAgent,
      newValues: {
        bot_id: input.bot_id,
        exchange: input.exchange,
        symbol: input.symbol,
        direction: input.direction,
        bot_mode: bot.mode,
      },
    })

    // Security log for live-mode signals (higher visibility).
    if (bot.mode === "live") {
      await writeSecurityLog(serviceClient, {
        userId: user.id,
        eventType: "live_manual_signal_created",
        severity: "info",
        ipAddress,
        userAgent,
        message: `Manual signal created for live bot: ${bot.name} — ${input.symbol} ${input.direction}`,
        metadata: {
          signal_id: signal.id,
          bot_id: input.bot_id,
          symbol: input.symbol,
        },
      })
    }

    // TODO(queue): Publish to PGMQ:
    // await publishToQueue(serviceClient, 'signal_received', {
    //   signal_id: signal.id,
    //   bot_id: input.bot_id,
    //   user_id: user.id,
    // })

    return jsonResponse(req, {
      signal_id: signal.id,
      bot_id: input.bot_id,
      symbol: input.symbol,
      direction: input.direction,
      status: "pending",
      created_at: signal.created_at,
      message:
        "Signal submitted. The agent pipeline will analyze this signal before any trade is considered.",
    })
  }),
)
