/**
 * Shared Zod schemas — single source of truth for client + server validation.
 *
 * Add domain schemas here as features are built. Each Edge Function payload
 * MUST have a schema in this package; the same schema runs on both sides.
 */
import { z } from "zod";

import { TRADE_MODE } from "@ta/types/enums";

// ── Bots ─────────────────────────────────────────────────────────────────────
export const BotCreateSchema = z.object({
  name:                  z.string().min(2).max(60),
  mode:                  z.enum(TRADE_MODE),
  exchange_account_id:   z.string().uuid().nullable(),
  trading_pairs:         z.array(z.string().min(3)).min(1).max(20),
  max_open_positions:    z.number().int().min(1).max(50),
  max_position_size_pct: z.number().min(0).max(100),
  risk_per_trade_pct:    z.number().min(0).max(100),
  max_daily_loss_pct:    z.number().min(0).max(100),
  base_currency:         z.string().min(2).max(8),
  requires_manual_approval: z.boolean(),
  trailing_stop_pct:     z.number().min(0).max(100).nullable().optional(),
});
export type BotCreateInput = z.infer<typeof BotCreateSchema>;

// ── User settings ────────────────────────────────────────────────────────────
export const UserSettingsUpdateSchema = z.object({
  trading_enabled:       z.boolean().optional(),
  daily_loss_limit_usd:  z.number().nonnegative().nullable().optional(),
  max_concurrent_trades: z.number().int().nonnegative().nullable().optional(),
});
export type UserSettingsUpdateInput = z.infer<typeof UserSettingsUpdateSchema>;

// ── Exchange accounts ────────────────────────────────────────────────────────
export const ExchangeAccountCreateSchema = z.object({
  exchange:   z.string().min(2).max(40),
  label:      z.string().min(1).max(60),
  api_key:    z.string().min(8),
  api_secret: z.string().min(8),
});
export type ExchangeAccountCreateInput = z.infer<typeof ExchangeAccountCreateSchema>;

// ── Decisions ────────────────────────────────────────────────────────────────
export const DecisionApproveSchema = z.object({ decision_id: z.string().uuid() });
export const DecisionRejectSchema  = z.object({
  decision_id: z.string().uuid(),
  reason:      z.string().min(1).max(400),
});

// ── Admin: platform settings ─────────────────────────────────────────────────
export const KillSwitchSchema = z.object({
  enabled: z.boolean(),
  reason:  z.string().min(1).max(400),
});

// ── Admin: reconciliation ────────────────────────────────────────────────────
export const ReconciliationResolveManualSchema = z.object({
  trade_id: z.string().uuid(),
  action:   z.enum(["mark_closed", "mark_failed", "reset_to_idle"]),
  reason:   z.string().min(1).max(400),
});
