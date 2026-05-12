// [EF-BOT-01] bot-control
//
// Safe state-machine transitions for bot lifecycle.
// All business logic around bot activation lives here — not in the client.
//
// Valid transitions:
//   draft   → active   (start)    requires active config
//   paused  → active   (start)    requires active config
//   stopped → active   (start)    requires active config
//   active  → paused   (pause)
//   active  → stopped  (stop)
//   paused  → stopped  (stop)
//   stopped → archived (archive)  requires no open trades
//   paused  → archived (archive)  requires no open trades
//   error   → archived (archive)
//   archived → stopped (unarchive)
//
// Live bot activation additionally requires:
//   - user_settings.real_trading_enabled = true
//   - subscription.real_trading_allowed = true
//   - active, connected, non-withdrawal exchange account linked

import {
  getAuthenticatedUser,
  getUserProfile,
  getUserSettings,
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
import { Bot, getRequestMeta } from "../_shared/types.ts"
import {
  BotControlSchema,
  validateRequestBody,
} from "../_shared/validation.ts"
import {
  assertUserOwnsBot,
  getActiveSafeExchangeAccountForBot,
} from "../_shared/ownership.ts"

// Maps each action to the required current status(es) and the resulting status.
const VALID_TRANSITIONS: Record<
  string,
  { from: string[]; to: string }
> = {
  start: { from: ["draft", "paused", "stopped"], to: "active" },
  pause: { from: ["active"], to: "paused" },
  stop: { from: ["active", "paused"], to: "stopped" },
  archive: { from: ["stopped", "paused", "error"], to: "archived" },
  unarchive: { from: ["archived"], to: "stopped" },
}

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

    // ── 2. Validate + ownership ───────────────────────────────────────────────
    const input = await validateRequestBody(req, BotControlSchema)

    const bot = await assertUserOwnsBot(serviceClient, user.id, input.bot_id)

    // ── 3. State machine validation ───────────────────────────────────────────
    const transition = VALID_TRANSITIONS[input.action]
    if (!transition) {
      throw Errors.badRequest(`Unknown action: ${input.action}`)
    }

    if (!transition.from.includes(bot.status)) {
      throw Errors.conflict(
        `Cannot ${input.action} a bot that is currently '${bot.status}'. ` +
        `This action requires status to be one of: ${transition.from.join(", ")}.`,
      )
    }

    // ── 4. Action-specific precondition checks ────────────────────────────────

    if (input.action === "start") {
      await validateStartPreconditions(bot, serviceClient, user.id)
    }

    if (input.action === "archive") {
      await validateArchivePreconditions(bot, serviceClient)
    }

    // ── 5. Perform the transition via service_role ────────────────────────────
    const now = new Date().toISOString()
    const newStatus = transition.to

    const updatePayload: Record<string, unknown> = {
      status: newStatus,
    }

    if (input.action === "archive") {
      updatePayload.is_archived = true
      updatePayload.archived_at = now
    }
    if (input.action === "unarchive") {
      updatePayload.is_archived = false
      updatePayload.archived_at = null
    }

    const { error: updateError } = await serviceClient
      .from("bots")
      .update(updatePayload)
      .eq("id", bot.id)
      .eq("user_id", user.id)
      .eq("status", bot.status) // Optimistic concurrency guard

    if (updateError) {
      throw Errors.internal(`Failed to ${input.action} bot`)
    }

    // ── 6. Audit + security logs ──────────────────────────────────────────────
    const auditAction = `BOT_${input.action.toUpperCase()}`
    const isLiveAction = bot.mode === "live"

    await writeAuditLog(serviceClient, {
      userId: user.id,
      actorRole: profile.role,
      action: auditAction,
      tableName: "bots",
      recordId: bot.id,
      oldValues: { status: bot.status, is_archived: bot.is_archived },
      newValues: { status: newStatus, ...updatePayload },
      ipAddress,
      userAgent,
      metadata: {
        bot_name: bot.name,
        bot_mode: bot.mode,
        reason: input.reason,
      },
    })

    // Live bot control gets a security log entry for visibility.
    if (isLiveAction || input.action === "archive") {
      await writeSecurityLog(serviceClient, {
        userId: user.id,
        eventType: `bot_${input.action}`,
        severity: isLiveAction ? "medium" : "info",
        ipAddress,
        userAgent,
        message: `Bot '${bot.name}' (${bot.mode}) ${input.action}ed: ${bot.status} → ${newStatus}`,
        metadata: {
          bot_id: bot.id,
          bot_mode: bot.mode,
          reason: input.reason,
        },
      })
    }

    return jsonResponse(req, {
      bot_id: bot.id,
      action: input.action,
      previous_status: bot.status,
      new_status: newStatus,
      message: `Bot successfully ${input.action}ed.`,
    })
  }),
)

// ── Precondition helpers ───────────────────────────────────────────────────

async function validateStartPreconditions(
  bot: Bot,
  serviceClient: ReturnType<typeof createSupabaseServiceClient>,
  userId: string,
): Promise<void> {
  // Must have an active configuration.
  if (!bot.active_config_id) {
    throw Errors.badRequest(
      "Bot has no active configuration. Create a bot config before starting.",
    )
  }

  const { data: config } = await serviceClient
    .from("bot_configs")
    .select("id, is_active")
    .eq("id", bot.active_config_id)
    .single()

  if (!config || !config.is_active) {
    throw Errors.badRequest(
      "Bot's active config is not currently active. Update the config and try again.",
    )
  }

  // Live bots have additional requirements.
  if (bot.mode === "live") {
    const [settings, subscription] = await Promise.all([
      serviceClient
        .from("user_settings")
        .select("real_trading_enabled, real_trading_requires_approval")
        .eq("user_id", userId)
        .single(),
      serviceClient
        .from("subscriptions")
        .select("real_trading_allowed, status")
        .eq("user_id", userId)
        .single(),
    ])

    if (!settings.data?.real_trading_enabled) {
      throw Errors.forbidden(
        "Real trading is not enabled on your account. " +
        "Enable it in your security settings before starting a live bot.",
      )
    }

    if (!subscription.data?.real_trading_allowed) {
      throw Errors.forbidden(
        "Your current subscription plan does not include live trading. " +
        "Upgrade to enable live bots.",
      )
    }

    if (!["active", "trialing"].includes(subscription.data?.status ?? "")) {
      throw Errors.forbidden(
        "Your subscription is not active. Resolve your billing to start live bots.",
      )
    }

    // Exchange account must be connected and safe.
    await getActiveSafeExchangeAccountForBot(serviceClient, bot)
  }
}

async function validateArchivePreconditions(
  bot: Bot,
  serviceClient: ReturnType<typeof createSupabaseServiceClient>,
): Promise<void> {
  // Cannot archive a bot that has open trades (would leave orphaned positions).
  const { count } = await serviceClient
    .from("trades")
    .select("id", { count: "exact", head: true })
    .eq("bot_id", bot.id)
    .eq("status", "open")

  if ((count ?? 0) > 0) {
    throw Errors.conflict(
      `Bot has ${count} open trade(s). Close all positions before archiving.`,
    )
  }
}
