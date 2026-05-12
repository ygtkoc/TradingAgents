// Mirrors relevant database column shapes.
// These are not exhaustive — only the fields consumed by Edge Functions.

export type UserRole =
  | "user"
  | "pro_user"
  | "admin"
  | "super_admin"
  | "security_admin"

export type BotMode = "paper" | "live" | "shadow"
export type BotStatus =
  | "draft"
  | "active"
  | "paused"
  | "stopped"
  | "archived"
  | "error"
export type TradeMode = "paper" | "live" | "shadow"
export type TradeDirection = "long" | "short" | "neutral"
export type ApprovalStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "auto_approved"
  | "expired"
export type SignalStatus =
  | "pending"
  | "processed"
  | "triggered"
  | "expired"
  | "cancelled"
export type SeverityLevel = "info" | "low" | "medium" | "high" | "critical"
export type SubscriptionStatus =
  | "trialing"
  | "active"
  | "past_due"
  | "cancelled"
  | "unpaid"
  | "paused"
export type SubscriptionPlan = "free" | "starter" | "pro" | "enterprise"

export interface Profile {
  id: string
  email: string
  role: UserRole
  is_banned: boolean
  subscription_status: SubscriptionStatus
  risk_level: number
  two_factor_enabled: boolean
}

export interface UserSettings {
  id: string
  user_id: string
  paper_trading_enabled: boolean
  real_trading_enabled: boolean
  real_trading_requires_approval: boolean
  max_open_trades: number
  default_risk_per_trade_pct: number
}

export interface Subscription {
  id: string
  user_id: string
  plan: SubscriptionPlan
  status: SubscriptionStatus
  max_bots: number
  max_trades_per_day: number
  real_trading_allowed: boolean
  current_period_end: string | null
}

export interface ExchangeAccount {
  id: string
  user_id: string
  exchange_name: string
  account_label: string
  connection_status: string
  can_read: boolean
  can_trade: boolean
  can_withdraw: boolean
  withdrawal_detected: boolean
  testnet: boolean
  is_active: boolean
}

export interface EncryptedApiKey {
  id: string
  user_id: string
  exchange_account_id: string
  key_status: string
  vault_key_id: string | null
  activated_at: string
  rotated_at: string | null
  revoked_at: string | null
}

export interface Bot {
  id: string
  user_id: string
  name: string
  mode: BotMode
  status: BotStatus
  is_archived: boolean
  active_config_id: string | null
  exchange_account_id: string | null
  requires_manual_approval: boolean
  max_open_positions: number
}

export interface TradeDecision {
  id: string
  user_id: string
  bot_id: string
  symbol: string
  direction: TradeDirection
  mode: TradeMode
  final_decision: string
  approval_status: ApprovalStatus
  manual_approval_required: boolean
  approved_by: string | null
  approved_at: string | null
  rejection_reason: string | null
}

export interface AuditLogParams {
  userId: string | null
  actorRole?: UserRole | null
  action: string
  tableName?: string
  recordId?: string
  oldValues?: Record<string, unknown>
  newValues?: Record<string, unknown>
  ipAddress?: string
  userAgent?: string
  source?: string
  sessionId?: string
  metadata?: Record<string, unknown>
}

export interface SecurityLogParams {
  userId?: string | null
  eventType: string
  severity: SeverityLevel
  source?: string
  ipAddress?: string
  userAgent?: string
  message: string
  metadata?: Record<string, unknown>
}

// Helpers to extract request context fields for logs.
export function getRequestMeta(req: Request): {
  ipAddress: string | undefined
  userAgent: string | undefined
} {
  return {
    ipAddress:
      req.headers.get("x-forwarded-for")?.split(",")[0].trim() ??
      req.headers.get("cf-connecting-ip") ??
      undefined,
    userAgent: req.headers.get("user-agent") ?? undefined,
  }
}
