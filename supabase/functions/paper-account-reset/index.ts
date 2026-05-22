// [EF-PAPER-02] paper-account-reset
//
// Resets the caller's paper trading state by delegating to public.paper_reset().
// The RPC is the single reset contract used by both the Edge Function and the
// authenticated local-dev fallback in the customer app.
//
// Does NOT touch:
//   - bots / exchange_accounts / agent_definitions / user_settings / profiles.
//
// Body:
//   { starting_balance?: number }
//
// Response:
//   { account_id, starting_balance, status, deleted: { signals, decisions, trades, events, account_events } }

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

    const requestedBalance = Number(body.starting_balance)
    if (
      body.starting_balance !== undefined &&
      (!Number.isFinite(requestedBalance) || requestedBalance <= 0 || requestedBalance > 1_000_000)
    ) {
      throw Errors.badRequest("starting_balance must be greater than 0 and at most 1000000")
    }

    const newStartingBalance =
      body.starting_balance !== undefined
        ? requestedBalance
        : null

    const { data: resetResult, error: resetErr } = await userClient.rpc("paper_reset", {
      p_user_id: user.id,
      p_starting_balance: newStartingBalance,
    })

    if (resetErr || !resetResult) {
      throw Errors.internal(
        "Failed to reset paper account via paper_reset(). " +
        "Deploy the latest database migration first: supabase db push. " +
        `RPC error: ${resetErr?.message ?? "empty response"}`,
      )
    }

    await writeAuditLog(serviceClient, {
      user_id:    user.id,
      action:     "paper_account_reset",
      record_id:  resetResult.account_id,
      table_name: "paper_accounts",
      source:     "edge_function",
      metadata:   {
        starting_balance: resetResult.starting_balance,
        deleted:          resetResult.deleted,
        ip: ipAddress, ua: userAgent,
      },
    })

    return jsonResponse(req, resetResult)
  })
)
