import { z } from "zod"
import { Errors } from "./errors.ts"

export { z }

// Parses and validates the JSON request body against a Zod schema.
// Returns the typed, validated data or throws an HttpError 422 with a
// human-readable summary of all validation failures.
export async function validateRequestBody<T>(
  req: Request,
  schema: z.ZodSchema<T>,
): Promise<T> {
  let body: unknown
  try {
    body = await req.json()
  } catch {
    throw Errors.badRequest("Request body must be valid JSON")
  }

  const result = schema.safeParse(body)
  if (!result.success) {
    const issues = result.error.issues
      .map((i) => {
        const path = i.path.length > 0 ? `${i.path.join(".")}: ` : ""
        return `${path}${i.message}`
      })
      .join("; ")
    throw Errors.unprocessable(`Validation failed — ${issues}`)
  }
  return result.data
}

// ── Reusable field schemas ───────────────────────────────────────────────────

export const uuidSchema = z.string().uuid("Must be a valid UUID")

export const botIdSchema = uuidSchema

export const exchangeAccountIdSchema = uuidSchema

export const symbolSchema = z
  .string()
  .min(2)
  .max(20)
  .regex(/^[A-Z0-9/]+$/, "Symbol must be uppercase alphanumeric (e.g. BTC/USDT)")

export const directionSchema = z.enum(["long", "short", "neutral"])

// ── Per-function request schemas ─────────────────────────────────────────────

export const StoreExchangeApiKeySchema = z.object({
  exchange_name: z
    .string()
    .min(1)
    .max(50)
    .regex(/^[a-z0-9_]+$/, "exchange_name must be lowercase alphanumeric with underscores"),
  account_label: z.string().min(1).max(100),
  api_key: z.string().min(10).max(512),
  api_secret: z.string().min(10).max(512),
  passphrase: z.string().max(256).optional(),
  testnet: z.boolean().optional().default(false),
})
export type StoreExchangeApiKeyInput = z.infer<typeof StoreExchangeApiKeySchema>

export const RevokeExchangeApiKeySchema = z.object({
  exchange_account_id: exchangeAccountIdSchema,
  reason: z.string().max(500).optional(),
})
export type RevokeExchangeApiKeyInput = z.infer<typeof RevokeExchangeApiKeySchema>

export const ManualTradeApprovalSchema = z.object({
  trade_decision_id: uuidSchema,
  action: z.enum(["approve", "reject"]),
  rejection_reason: z.string().max(1000).optional(),
})
export type ManualTradeApprovalInput = z.infer<typeof ManualTradeApprovalSchema>

export const CreateManualSignalSchema = z.object({
  bot_id: botIdSchema,
  exchange: z.string().min(1).max(50),
  symbol: symbolSchema,
  direction: directionSchema,
  metadata: z.record(z.unknown()).optional().default({}),
})
export type CreateManualSignalInput = z.infer<typeof CreateManualSignalSchema>

export const BotControlSchema = z.object({
  bot_id: botIdSchema,
  action: z.enum(["start", "pause", "stop", "archive", "unarchive"]),
  reason: z.string().max(500).optional(),
})
export type BotControlInput = z.infer<typeof BotControlSchema>

export const ExchangeHealthCheckSchema = z.object({
  exchange_account_id: exchangeAccountIdSchema,
})
export type ExchangeHealthCheckInput = z.infer<typeof ExchangeHealthCheckSchema>

export const AdminSecurityActionSchema = z.object({
  action: z.enum([
    "resolve_security_log",
    "review_red_team_report",
    "resolve_database_schema_audit",
    "pause_user_trading",
    "ban_user",
    "unban_user",
    "global_pause_placeholder",
  ]),
  target_id: uuidSchema,
  notes: z.string().max(2000).optional(),
})
export type AdminSecurityActionInput = z.infer<typeof AdminSecurityActionSchema>

export const CreateNotificationSchema = z.object({
  user_id: uuidSchema,
  type: z.enum([
    "trade_opened",
    "trade_closed",
    "bot_error",
    "bot_paused",
    "risk_alert",
    "security_alert",
    "system_update",
    "subscription_update",
    "manual_approval_required",
    "agent_veto",
    "backtest_complete",
    "api_key_expiring",
  ]),
  title: z.string().min(1).max(200),
  message: z.string().min(1).max(2000),
  priority: z.number().int().min(1).max(5).optional().default(3),
  related_table: z.string().max(100).optional(),
  related_id: uuidSchema.optional(),
  metadata: z.record(z.unknown()).optional().default({}),
})
export type CreateNotificationInput = z.infer<typeof CreateNotificationSchema>
