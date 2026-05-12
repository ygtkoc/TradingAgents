/**
 * String-literal enums mirroring backend Python enums exactly.
 * Source of truth: backend `db/models.py` (execution-engine + position-engine).
 *
 * Whenever a value here changes, the corresponding Postgres enum must also be
 * migrated. Frontend code SHOULD use the typed unions below rather than raw
 * strings.
 */

// ── Trade ────────────────────────────────────────────────────────────────────
export const TRADE_STATUS = ["open", "closed", "cancelled", "failed", "simulated", "pending"] as const;
export type TradeStatus = (typeof TRADE_STATUS)[number];

export const TRADE_MODE = ["paper", "live", "shadow"] as const;
export type TradeMode = (typeof TRADE_MODE)[number];

export const TRADE_DIRECTION = ["long", "short", "neutral"] as const;
export type TradeDirection = (typeof TRADE_DIRECTION)[number];

// ── Lifecycle (position-engine) ──────────────────────────────────────────────
export const LIFECYCLE_STATUS = [
  "idle",
  "monitoring",
  "closing",
  "closed",
  "failed",
  "needs_reconciliation",
] as const;
export type LifecycleStatus = (typeof LIFECYCLE_STATUS)[number];

// ── Bot ──────────────────────────────────────────────────────────────────────
export const BOT_STATUS = ["draft", "active", "paused", "stopped", "archived", "error"] as const;
export type BotStatus = (typeof BOT_STATUS)[number];

// ── Trade decision ───────────────────────────────────────────────────────────
export const FINAL_DECISION = [
  "open_long",
  "open_short",
  "wait",
  "reject",
  "pause_trading",
  "manual_approval_required",
] as const;
export type FinalDecision = (typeof FINAL_DECISION)[number];

export const APPROVAL_STATUS = [
  "approved",
  "auto_approved",
  "pending",
  "rejected",
  "manual_review",
] as const;
export type ApprovalStatus = (typeof APPROVAL_STATUS)[number];

export const EXECUTION_STATUS = ["executing", "executed", "failed", "skipped"] as const;
export type ExecutionStatus = (typeof EXECUTION_STATUS)[number];

// ── Severity (logs) ──────────────────────────────────────────────────────────
export const SEVERITY = ["info", "low", "medium", "high", "critical"] as const;
export type Severity = (typeof SEVERITY)[number];

// ── User role (admin gating) ─────────────────────────────────────────────────
export const USER_ROLE = ["user", "admin"] as const;
export type UserRole = (typeof USER_ROLE)[number];
