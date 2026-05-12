// [EF-TRADE-01] manual-trade-approval
//
// The only write path for a user to influence the trade_decisions table.
// Validates strict preconditions before making any changes:
//   - Decision must belong to the caller.
//   - Decision must have manual_approval_required = true.
//   - Decision must currently be in 'pending' approval_status.
//
// This function does NOT create a trade row. Trade execution is delegated
// to the Python Execution Agent which polls for approved decisions.
//
// TODO(queue): Publish an 'execution_requested' event to PGMQ after approval
//   so the Execution Agent can pick it up without polling.

import { getAuthenticatedUser, getUserProfile } from "../_shared/auth.ts"
import { writeAuditLog } from "../_shared/audit.ts"
import { handleCors } from "../_shared/cors.ts"
import { Errors } from "../_shared/errors.ts"
import { jsonResponse, withErrorHandler } from "../_shared/response.ts"
import {
  createSupabaseServiceClient,
  createSupabaseUserClient,
} from "../_shared/supabase.ts"
import { getRequestMeta } from "../_shared/types.ts"
import {
  ManualTradeApprovalSchema,
  validateRequestBody,
} from "../_shared/validation.ts"
import { assertUserOwnsTradeDecision } from "../_shared/ownership.ts"

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

    // ── 2. Validate input ────────────────────────────────────────────────────
    const input = await validateRequestBody(req, ManualTradeApprovalSchema)

    if (input.action === "reject" && !input.rejection_reason?.trim()) {
      throw Errors.unprocessable(
        "rejection_reason is required when action is 'reject'",
      )
    }

    // ── 3. Ownership + precondition checks ───────────────────────────────────
    const decision = await assertUserOwnsTradeDecision(
      serviceClient,
      user.id,
      input.trade_decision_id,
    )

    if (!decision.manual_approval_required) {
      throw Errors.badRequest(
        "This trade decision does not require manual approval",
      )
    }

    if (decision.approval_status !== "pending") {
      throw Errors.conflict(
        `Trade decision has already been ${decision.approval_status}. No changes made.`,
      )
    }

    const now = new Date().toISOString()

    // ── 4. Apply the approval or rejection ───────────────────────────────────
    if (input.action === "approve") {
      const { error } = await serviceClient
        .from("trade_decisions")
        .update({
          approval_status: "approved",
          approved_by: user.id,
          approved_at: now,
          rejection_reason: null,
        })
        .eq("id", decision.id)
        .eq("user_id", user.id)   // Belt-and-suspenders ownership check
        .eq("approval_status", "pending") // Optimistic concurrency guard

      if (error) throw Errors.internal("Failed to approve trade decision")

      await writeAuditLog(serviceClient, {
        userId: user.id,
        actorRole: profile.role,
        action: "TRADE_DECISION_APPROVED",
        tableName: "trade_decisions",
        recordId: decision.id,
        oldValues: { approval_status: "pending" },
        newValues: {
          approval_status: "approved",
          approved_by: user.id,
          approved_at: now,
        },
        ipAddress,
        userAgent,
        metadata: {
          symbol: decision.symbol,
          direction: decision.direction,
          final_decision: decision.final_decision,
          bot_id: decision.bot_id,
        },
      })

      // TODO(queue): Publish to PGMQ 'trade_execution' queue:
      // await publishToQueue(serviceClient, 'trade_execution', {
      //   trade_decision_id: decision.id,
      //   bot_id: decision.bot_id,
      //   user_id: user.id,
      //   approved_at: now,
      // })

      return jsonResponse(req, {
        trade_decision_id: decision.id,
        status: "approved",
        approved_at: now,
        message:
          "Trade decision approved. Execution has been queued for the agent engine.",
      })
    } else {
      // action === 'reject'
      const { error } = await serviceClient
        .from("trade_decisions")
        .update({
          approval_status: "rejected",
          rejection_reason: input.rejection_reason!,
          approved_by: user.id,
          approved_at: now,
        })
        .eq("id", decision.id)
        .eq("user_id", user.id)
        .eq("approval_status", "pending")

      if (error) throw Errors.internal("Failed to reject trade decision")

      await writeAuditLog(serviceClient, {
        userId: user.id,
        actorRole: profile.role,
        action: "TRADE_DECISION_REJECTED",
        tableName: "trade_decisions",
        recordId: decision.id,
        oldValues: { approval_status: "pending" },
        newValues: {
          approval_status: "rejected",
          rejection_reason: input.rejection_reason,
        },
        ipAddress,
        userAgent,
        metadata: {
          symbol: decision.symbol,
          direction: decision.direction,
          bot_id: decision.bot_id,
        },
      })

      return jsonResponse(req, {
        trade_decision_id: decision.id,
        status: "rejected",
        rejected_at: now,
        rejection_reason: input.rejection_reason,
      })
    }
  }),
)
