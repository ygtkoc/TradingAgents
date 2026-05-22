// [EF-PAPER-01] paper-account-create
//
// Creates (or upserts) the caller's paper_accounts row with a chosen
// starting_balance. If a row already exists, this becomes a no-op for the
// id and updates only `starting_balance`, `metadata`, and `updated_at` —
// it does NOT reset the balance. Use paper-account-reset for that.
//
// Body:
//   { starting_balance: number, currency?: "USD" }
//
// Response:
//   { account_id: string, starting_balance: number, balance: number, status: string }
//
// Auth: requires authenticated user. Service role inside the function
// bypasses RLS for the upsert.
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

const MIN_BALANCE = 1
const MAX_BALANCE = 1_000_000

Deno.serve((req: Request) =>
  withErrorHandler(req, async () => {
    const preflight = handleCors(req)
    if (preflight) return preflight
    if (req.method !== "POST") throw Errors.badRequest("Method not allowed")

    const { ipAddress, userAgent } = getRequestMeta(req)
    const userClient    = createSupabaseUserClient(req)
    const serviceClient = createSupabaseServiceClient()
    const user          = await getAuthenticatedUser(userClient)
    console.info("paper_account.create.start", { user_id: user.id, ip: ipAddress })

    let body: { starting_balance?: number; currency?: string } = {}
    try { body = await req.json() } catch { /* ignore */ }

    const startingBalance = Number(body.starting_balance)
    if (!Number.isFinite(startingBalance) ||
         startingBalance < MIN_BALANCE  ||
         startingBalance > MAX_BALANCE) {
      throw Errors.badRequest(
        `starting_balance must be between ${MIN_BALANCE} and ${MAX_BALANCE}`,
      )
    }

    const currency = (body.currency ?? "USD").toUpperCase().slice(0, 8)

    // Read existing row (the auto-trigger creates it on user signup).
    const { data: existing, error: readErr } = await serviceClient
      .from("paper_accounts")
      .select("id, balance, status")
      .eq("user_id", user.id)
      .maybeSingle()

    if (readErr && readErr.code !== "PGRST116") {
      console.error("paper_account.create.failed", {
        user_id: user.id,
        stage: "read_existing",
        error: readErr.message,
        code: readErr.code,
      })
      throw Errors.internal("Failed to read paper account: " + readErr.message)
    }

    // First-time create vs update-only-starting-balance
    let accountId: string
    let balance:   number
    let status:    string

    if (!existing) {
      const { data: ins, error: insErr } = await serviceClient
        .from("paper_accounts")
        .insert({
          user_id:          user.id,
          currency,
          starting_balance: startingBalance,
          balance:          startingBalance,
          reserved_balance: 0,
          status:           "active",
          started_at:       new Date().toISOString(),
          paused_at:        null,
          metadata:         { created_via: "paper-account-create" },
        })
        .select("id, balance, status")
        .single()
      if (insErr?.code === "23505") {
        const { data: racedExisting, error: racedErr } = await serviceClient
          .from("paper_accounts")
          .select("id, balance, status")
          .eq("user_id", user.id)
          .maybeSingle()
        if (racedErr || !racedExisting) {
          console.error("paper_account.create.failed", {
            user_id: user.id,
            stage: "recover_existing_after_conflict",
            error: racedErr?.message ?? insErr.message,
            code: racedErr?.code ?? insErr.code,
          })
          throw Errors.internal("Failed to recover paper account after conflict")
        }
        const { error: updErr } = await serviceClient
          .from("paper_accounts")
          .update({
            currency,
            starting_balance: startingBalance,
            status:           "active",
            started_at:       new Date().toISOString(),
            paused_at:        null,
            metadata:         { last_updated_via: "paper-account-create" },
          })
          .eq("id", racedExisting.id)
          .eq("user_id", user.id)
        if (updErr) {
          console.error("paper_account.create.failed", {
            user_id: user.id,
            stage: "update_after_conflict",
            error: updErr.message,
            code: updErr.code,
          })
          throw Errors.internal("Failed to update paper account after conflict: " + updErr.message)
        }
        console.info("paper_account.create.existing", {
          user_id: user.id,
          account_id: racedExisting.id,
        })
        accountId = racedExisting.id; balance = racedExisting.balance; status = "active"
      } else if (insErr || !ins) {
        console.error("paper_account.create.failed", {
          user_id: user.id,
          stage: "insert",
          error: insErr?.message ?? "no row",
          code: insErr?.code,
        })
        throw Errors.internal("Failed to create paper account: " + (insErr?.message ?? "no row"))
      } else {
        console.info("paper_account.create.created", {
          user_id: user.id,
          account_id: ins.id,
        })
        accountId = ins.id; balance = ins.balance; status = ins.status
      }
    } else {
      const { error: updErr } = await serviceClient
        .from("paper_accounts")
        .update({
          currency,
          starting_balance: startingBalance,
          status:           "active",
          started_at:       new Date().toISOString(),
          paused_at:        null,
          metadata:         { last_updated_via: "paper-account-create" },
        })
        .eq("id", existing.id)
        .eq("user_id", user.id)
      if (updErr) {
        console.error("paper_account.create.failed", {
          user_id: user.id,
          stage: "update_existing",
          error: updErr.message,
          code: updErr.code,
        })
        throw Errors.internal("Failed to update paper account: " + updErr.message)
      }
      console.info("paper_account.create.existing", {
        user_id: user.id,
        account_id: existing.id,
      })
      accountId = existing.id; balance = existing.balance; status = "active"
    }

    await writeAuditLog(serviceClient, {
      user_id:    user.id,
      action:     "paper_account_create",
      record_id:  accountId,
      table_name: "paper_accounts",
      source:     "edge_function",
      metadata:   { starting_balance: startingBalance, currency, ip: ipAddress, ua: userAgent },
    })

    return jsonResponse(req, {
      account_id:       accountId,
      starting_balance: startingBalance,
      balance,
      status,
    })
  })
)
