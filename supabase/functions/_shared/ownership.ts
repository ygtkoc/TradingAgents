import { SupabaseClient } from "@supabase/supabase-js"
import { Errors } from "./errors.ts"
import { Bot, ExchangeAccount, TradeDecision } from "./types.ts"

// ── Bot ownership ────────────────────────────────────────────────────────────

export async function assertUserOwnsBot(
  serviceClient: SupabaseClient,
  userId: string,
  botId: string,
): Promise<Bot> {
  const { data, error } = await serviceClient
    .from("bots")
    .select(
      "id, user_id, name, mode, status, is_archived, active_config_id, exchange_account_id, requires_manual_approval, max_open_positions",
    )
    .eq("id", botId)
    .single()

  if (error || !data) throw Errors.notFound("Bot not found")
  if ((data as Bot).user_id !== userId) {
    throw Errors.forbidden("You do not have access to this bot")
  }
  return data as Bot
}

// ── Exchange account ownership ───────────────────────────────────────────────

export async function assertUserOwnsExchangeAccount(
  serviceClient: SupabaseClient,
  userId: string,
  accountId: string,
): Promise<ExchangeAccount> {
  const { data, error } = await serviceClient
    .from("exchange_accounts")
    .select("*")
    .eq("id", accountId)
    .single()

  if (error || !data) throw Errors.notFound("Exchange account not found")
  if ((data as ExchangeAccount).user_id !== userId) {
    throw Errors.forbidden("You do not have access to this exchange account")
  }
  return data as ExchangeAccount
}

// ── Trade decision ownership ──────────────────────────────────────────────────

export async function assertUserOwnsTradeDecision(
  serviceClient: SupabaseClient,
  userId: string,
  decisionId: string,
): Promise<TradeDecision> {
  const { data, error } = await serviceClient
    .from("trade_decisions")
    .select(
      "id, user_id, bot_id, symbol, direction, mode, final_decision, approval_status, manual_approval_required, approved_by, approved_at, rejection_reason",
    )
    .eq("id", decisionId)
    .single()

  if (error || !data) throw Errors.notFound("Trade decision not found")
  if ((data as TradeDecision).user_id !== userId) {
    throw Errors.forbidden("You do not have access to this trade decision")
  }
  return data as TradeDecision
}

// ── Bot activation preflight checks ─────────────────────────────────────────

// Returns the active exchange account for a live bot, or throws with a
// descriptive message explaining what is missing.
export async function getActiveSafeExchangeAccountForBot(
  serviceClient: SupabaseClient,
  bot: Bot,
): Promise<ExchangeAccount> {
  if (!bot.exchange_account_id) {
    throw Errors.badRequest(
      "Live bot requires a linked exchange account. Add one before starting.",
    )
  }

  const { data, error } = await serviceClient
    .from("exchange_accounts")
    .select("*")
    .eq("id", bot.exchange_account_id)
    .single()

  if (error || !data) {
    throw Errors.badRequest("Linked exchange account not found")
  }

  const account = data as ExchangeAccount

  if (!account.is_active) {
    throw Errors.badRequest(
      "Linked exchange account is deactivated. Reactivate or link a different account.",
    )
  }
  if (account.connection_status !== "connected") {
    throw Errors.badRequest(
      `Exchange account connection status is '${account.connection_status}'. Reconnect before starting a live bot.`,
    )
  }
  if (account.withdrawal_detected) {
    throw Errors.forbidden(
      "Linked exchange account has withdrawal permissions enabled. " +
      "Revoke the key and add a trade-only key to proceed.",
    )
  }
  if (!account.can_trade) {
    throw Errors.badRequest(
      "Linked API key does not have trading permissions.",
    )
  }

  return account
}
