// [EF-NOTIFY-01] create-notification
//
// Trusted notification creation endpoint.
// Only admin-role callers can invoke this from the client side.
// The Python Agent Engine uses service_role directly — it does not
// need to call this endpoint (it can INSERT notifications directly
// via service_role, bypassing RLS).
//
// This endpoint exists for:
//   - Admin-initiated system announcements
//   - Test/preview notifications from the admin dashboard
//   - Any server-side system that has a user JWT but not service_role

import {
  getAuthenticatedUser,
  getUserProfile,
  requireAdmin,
} from "../_shared/auth.ts"
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
  CreateNotificationSchema,
  validateRequestBody,
} from "../_shared/validation.ts"

Deno.serve((req: Request) =>
  withErrorHandler(req, async () => {
    const preflight = handleCors(req)
    if (preflight) return preflight

    if (req.method !== "POST") throw Errors.badRequest("Method not allowed")

    const { ipAddress, userAgent } = getRequestMeta(req)

    // ── 1. Auth + role check ──────────────────────────────────────────────────
    const userClient = createSupabaseUserClient(req)
    const serviceClient = createSupabaseServiceClient()

    const user = await getAuthenticatedUser(userClient)
    const profile = await getUserProfile(serviceClient, user.id)

    requireAdmin(profile)

    // ── 2. Validate input ────────────────────────────────────────────────────
    const input = await validateRequestBody(req, CreateNotificationSchema)

    // ── 3. Verify target user exists ──────────────────────────────────────────
    const { data: targetProfile, error: targetError } = await serviceClient
      .from("profiles")
      .select("id")
      .eq("id", input.user_id)
      .single()

    if (targetError || !targetProfile) {
      throw Errors.notFound(`Target user ${input.user_id} not found`)
    }

    // ── 4. Insert notification via service_role ───────────────────────────────
    const { data: notification, error: insertError } = await serviceClient
      .from("notifications")
      .insert({
        user_id: input.user_id,
        type: input.type,
        title: input.title,
        message: input.message,
        priority: input.priority,
        related_table: input.related_table ?? null,
        related_id: input.related_id ?? null,
        metadata: {
          ...input.metadata,
          created_by_admin: user.id,
        },
      })
      .select("id, created_at")
      .single()

    if (insertError || !notification) {
      throw Errors.internal("Failed to create notification")
    }

    await writeAuditLog(serviceClient, {
      userId: user.id,
      actorRole: profile.role,
      action: "NOTIFICATION_CREATED",
      tableName: "notifications",
      recordId: notification.id,
      ipAddress,
      userAgent,
      newValues: {
        target_user_id: input.user_id,
        type: input.type,
        title: input.title,
      },
    })

    return jsonResponse(req, {
      notification_id: notification.id,
      user_id: input.user_id,
      type: input.type,
      created_at: notification.created_at,
    })
  }),
)
