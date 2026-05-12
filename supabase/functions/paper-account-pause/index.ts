// [EF-PAPER-04] paper-account-pause
//
// Pauses autonomous paper trading for the caller. The signal generator
// will stop seeding signals for this user's paper bots until resumed.
import { getAuthenticatedUser } from "../_shared/auth.ts"
import { writeAuditLog } from "../_shared/audit.ts"
import { handleCors } from "../_shared/cors.ts"
import { Errors } from "../_shared/errors.ts"
import { jsonResponse, withErrorHandler } from "../_shared/response.ts"
import {
  createSupabaseServiceClient,
  createSupabaseUserClient,
} from "../_shared/supabase.ts"

Deno.serve((req: Request) =>
  withErrorHandler(req, async () => {
    const preflight = handleCors(req)
    if (preflight) return preflight
    if (req.method !== "POST") throw Errors.badRequest("Method not allowed")

    const userClient    = createSupabaseUserClient(req)
    const serviceClient = createSupabaseServiceClient()
    const user          = await getAuthenticatedUser(userClient)

    const { data: acct, error: readErr } = await serviceClient
      .from("paper_accounts")
      .select("id, status")
      .eq("user_id", user.id)
      .maybeSingle()
    if (readErr || !acct) throw Errors.notFound("paper_accounts row missing for user")

    const { error: updErr } = await serviceClient
      .from("paper_accounts")
      .update({
        status:    "paused",
        paused_at: new Date().toISOString(),
      })
      .eq("id", acct.id)
      .eq("user_id", user.id)
    if (updErr) throw Errors.internal("Failed to pause paper account: " + updErr.message)

    await writeAuditLog(serviceClient, {
      user_id:    user.id,
      action:     "paper_account_pause",
      record_id:  acct.id,
      table_name: "paper_accounts",
      source:     "edge_function",
      metadata:   { previous_status: acct.status },
    })

    return jsonResponse(req, { account_id: acct.id, status: "paused" })
  })
)
