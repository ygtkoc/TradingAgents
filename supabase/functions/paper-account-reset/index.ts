// [EF-PAPER-02] paper-account-reset
//
// Resets the caller's paper trading state:
//   • Deletes user's paper trade_events / trades / trade_decisions / signals.
//   • Resets paper_accounts.balance to (provided) starting_balance, realised=0.
//   • Sets status='paused' and stamps reset_at.
//
// Does NOT touch:
//   • bots / exchange_accounts / agent_definitions / user_settings / profiles.
//
// Body:
//   { starting_balance?: number }   // optional — defaults to current starting_balance
//
// Response:
//   { account_id, starting_balance, deleted: { signals, decisions, trades, events } }

import { getAuthenticatedUser } from "../_shared/auth.ts"
import { writeAuditLog } from "../_shared/audit.ts"
import { handleCors } from "../_shared/cors.ts"
import { Errors } from "../_shared/errors.ts"
import { jsonResponse, withErrorHandler } from "../_shared/response.ts"
import {
  createSupabaseServiceClient,
  createSupabaseUserClient,
} from "../_shared/supabase.ts"
import { getRequestMeta } from "../_shared/types.ts"

Deno.serve((req: Request) =>
  withErrorHandler(req, async () => {
    const preflight = handleCors(req)
    if (preflight) return preflight
    if (req.method !== "POST") throw Errors.badRequest("Method not allowed")

    const { ipAddress, userAgent } = getRequestMeta(req)
    const userClient    = createSupabaseUserClient(req)
    const serviceClient = createSupabaseServiceClient()
    const user          = await getAuthenticatedUser(userClient)

    let body: { starting_balance?: number } = {}
    try { body = await req.json() } catch { /* ignore */ }

    const { data: acct, error: readErr } = await serviceClient
      .from("paper_accounts")
      .select("id, starting_balance")
      .eq("user_id", user.id)
      .maybeSingle()
    if (readErr || !acct) {
      throw Errors.notFound("paper_accounts row missing for user")
    }

    const requestedBalance = Number(body.starting_balance)
    const newStartingBalance =
      Number.isFinite(requestedBalance) && requestedBalance > 0 && requestedBalance <= 1_000_000
        ? requestedBalance
        : Number(acct.starting_balance)

    // Delete only THIS user's paper rows (mode='paper' for trades).
    const counts: Record<string, number> = {
      signals: 0, decisions: 0, trades: 0, events: 0, account_events: 0,
    }

    // 1. trade_events for paper trades and their decisions
    const { data: paperTradeIds } = await serviceClient
      .from("trades")
      .select("id")
      .eq("user_id", user.id)
      .eq("mode", "paper")
    const ids = (paperTradeIds ?? []).map((r: { id: string }) => r.id)

    const { data: paperDecisionIds } = await serviceClient
      .from("trade_decisions")
      .select("id")
      .eq("user_id", user.id)
      .eq("mode", "paper")
    const decisionIds = (paperDecisionIds ?? []).map((r: { id: string }) => r.id)

    if (ids.length > 0) {
      const { count: evCount } = await serviceClient
        .from("trade_events")
        .delete({ count: "exact" })
        .in("trade_id", ids)
      counts.events = evCount ?? 0
    }
    if (decisionIds.length > 0) {
      const { count: evByDecisionCount } = await serviceClient
        .from("trade_events")
        .delete({ count: "exact" })
        .in("trade_decision_id", decisionIds)
      counts.events += evByDecisionCount ?? 0
    }

    // 2. paper trade_decisions (before trades because linked_trade_id references trades)
    const { count: dCount } = await serviceClient
      .from("trade_decisions")
      .delete({ count: "exact" })
      .eq("user_id", user.id)
      .eq("mode", "paper")
    counts.decisions = dCount ?? 0

    // 3. paper trades themselves
    const { count: tCount } = await serviceClient
      .from("trades")
      .delete({ count: "exact" })
      .eq("user_id", user.id)
      .eq("mode", "paper")
    counts.trades = tCount ?? 0

    // 4. paper signals
    const { count: sCount } = await serviceClient
      .from("signals")
      .delete({ count: "exact" })
      .eq("user_id", user.id)
    counts.signals = sCount ?? 0

    // 5. paper_account_events
    const { count: peCount } = await serviceClient
      .from("paper_account_events")
      .delete({ count: "exact" })
      .eq("user_id", user.id)
    counts.account_events = peCount ?? 0

    // 6. reset balance + status
    const resetAt = new Date().toISOString()
    const { error: updErr } = await serviceClient
      .from("paper_accounts")
      .update({
        starting_balance: newStartingBalance,
        balance:          newStartingBalance,
        realized_pnl:     0,
        unrealized_pnl:   0,
        status:           "paused",
        reset_at:         resetAt,
        started_at:       null,
        paused_at:        resetAt,
        metadata:         { last_reset_via: "paper-account-reset" },
      })
      .eq("id", acct.id)
      .eq("user_id", user.id)
    if (updErr) throw Errors.internal("Failed to reset paper account: " + updErr.message)

    await writeAuditLog(serviceClient, {
      user_id:    user.id,
      action:     "paper_account_reset",
      record_id:  acct.id,
      table_name: "paper_accounts",
      source:     "edge_function",
      metadata:   {
        starting_balance: newStartingBalance,
        deleted:          counts,
        ip: ipAddress, ua: userAgent,
      },
    })

    return jsonResponse(req, {
      account_id:       acct.id,
      starting_balance: newStartingBalance,
      status:           "paused",
      deleted:          counts,
    })
  })
)
