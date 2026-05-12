// [EF-ADMIN-01] admin-security-action
//
// Privileged operations for the admin.ornek.com dashboard.
// Each action is gated by the minimum required role.
//
// Role requirements:
//   resolve_security_log          → security_admin or super_admin
//   review_red_team_report        → security_admin or super_admin
//   resolve_database_schema_audit → security_admin or super_admin
//   pause_user_trading            → admin or super_admin
//   ban_user                      → super_admin only
//   unban_user                    → super_admin only
//   global_pause_placeholder      → super_admin only (placeholder for future)
//
// All mutations use service_role and are paired with audit_logs rows.
// Admins cannot use this endpoint to read encrypted API key payloads.

import {
  getAuthenticatedUser,
  getUserProfile,
  requireAdmin,
  requireSecurityAdmin,
  requireSuperAdmin,
} from "../_shared/auth.ts"
import { writeAuditLog, writeSecurityLog } from "../_shared/audit.ts"
import { handleCors } from "../_shared/cors.ts"
import { Errors } from "../_shared/errors.ts"
import { jsonResponse, withErrorHandler } from "../_shared/response.ts"
import {
  createSupabaseServiceClient,
  createSupabaseUserClient,
} from "../_shared/supabase.ts"
import { getRequestMeta } from "../_shared/types.ts"
import {
  AdminSecurityActionSchema,
  validateRequestBody,
} from "../_shared/validation.ts"

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

    // All admin actions require at minimum the admin role.
    requireAdmin(profile)

    // ── 2. Validate input ────────────────────────────────────────────────────
    const input = await validateRequestBody(req, AdminSecurityActionSchema)

    // ── 3. Per-action role gate + execution ───────────────────────────────────
    const now = new Date().toISOString()
    let result: Record<string, unknown>

    switch (input.action) {
      // ── Resolve security log ───────────────────────────────────────────────
      case "resolve_security_log": {
        requireSecurityAdmin(profile)

        const { data: log, error: fetchError } = await serviceClient
          .from("security_logs")
          .select("id, resolved")
          .eq("id", input.target_id)
          .single()

        if (fetchError || !log) throw Errors.notFound("Security log not found")
        if (log.resolved) throw Errors.conflict("Security log already resolved")

        const { error } = await serviceClient
          .from("security_logs")
          .update({
            resolved: true,
            resolved_by: user.id,
            resolved_at: now,
            metadata: { resolution_notes: input.notes },
          })
          .eq("id", input.target_id)

        if (error) throw Errors.internal("Failed to resolve security log")

        result = { resolved: true, resolved_at: now }
        break
      }

      // ── Review red team report ─────────────────────────────────────────────
      case "review_red_team_report": {
        requireSecurityAdmin(profile)

        const { data: report, error: fetchError } = await serviceClient
          .from("red_team_reports")
          .select("id, status")
          .eq("id", input.target_id)
          .single()

        if (fetchError || !report) {
          throw Errors.notFound("Red team report not found")
        }

        const { error } = await serviceClient
          .from("red_team_reports")
          .update({
            admin_reviewed: true,
            reviewed_by: user.id,
            reviewed_at: now,
            status: "acknowledged",
            review_notes: input.notes ?? null,
          })
          .eq("id", input.target_id)

        if (error) throw Errors.internal("Failed to update red team report")

        result = { reviewed: true, reviewed_at: now }
        break
      }

      // ── Resolve DB schema audit ────────────────────────────────────────────
      case "resolve_database_schema_audit": {
        requireSecurityAdmin(profile)

        const { error } = await serviceClient
          .from("database_schema_audits")
          .update({
            status: "resolved",
            reviewed_by: user.id,
            reviewed_at: now,
          })
          .eq("id", input.target_id)

        if (error) throw Errors.internal("Failed to update schema audit")

        result = { resolved: true, resolved_at: now }
        break
      }

      // ── Pause user trading ─────────────────────────────────────────────────
      case "pause_user_trading": {
        requireAdmin(profile) // admin+ can pause trading

        // Prevent admins from pausing their own trading or super_admin's.
        const { data: targetProfile } = await serviceClient
          .from("profiles")
          .select("id, role, email")
          .eq("id", input.target_id)
          .single()

        if (!targetProfile) throw Errors.notFound("User not found")
        if (targetProfile.id === user.id) {
          throw Errors.forbidden("You cannot modify your own trading permissions")
        }
        if (targetProfile.role === "super_admin") {
          throw Errors.forbidden("Cannot modify super_admin trading permissions")
        }

        // Disable real trading and pause all active live bots for the target user.
        const [settingsResult, botsResult] = await Promise.all([
          serviceClient
            .from("user_settings")
            .update({ real_trading_enabled: false })
            .eq("user_id", input.target_id),
          serviceClient
            .from("bots")
            .update({ status: "paused" })
            .eq("user_id", input.target_id)
            .eq("mode", "live")
            .eq("status", "active"),
        ])

        if (settingsResult.error || botsResult.error) {
          throw Errors.internal("Failed to pause user trading")
        }

        await writeSecurityLog(serviceClient, {
          userId: input.target_id,
          eventType: "admin_trading_paused",
          severity: "high",
          ipAddress,
          userAgent,
          message: `Trading paused for user ${targetProfile.email} by admin ${profile.email}`,
          metadata: { admin_id: user.id, notes: input.notes },
        })

        result = { user_id: input.target_id, trading_paused: true }
        break
      }

      // ── Ban user ───────────────────────────────────────────────────────────
      case "ban_user": {
        requireSuperAdmin(profile)

        const { data: targetProfile } = await serviceClient
          .from("profiles")
          .select("id, role, email, is_banned")
          .eq("id", input.target_id)
          .single()

        if (!targetProfile) throw Errors.notFound("User not found")
        if (targetProfile.id === user.id) {
          throw Errors.forbidden("You cannot ban yourself")
        }
        if (targetProfile.is_banned) {
          throw Errors.conflict("User is already banned")
        }
        if (["admin", "super_admin", "security_admin"].includes(targetProfile.role)) {
          throw Errors.forbidden("Cannot ban admin-level accounts via this endpoint")
        }

        // Ban user, stop all their bots, deactivate exchange accounts.
        await Promise.all([
          serviceClient.from("profiles").update({
            is_banned: true,
            ban_reason: input.notes ?? "Banned by super_admin",
            banned_at: now,
            banned_by: user.id,
          }).eq("id", input.target_id),

          serviceClient.from("bots").update({ status: "stopped" })
            .eq("user_id", input.target_id)
            .in("status", ["active", "paused"]),

          serviceClient.from("exchange_accounts").update({
            is_active: false,
            deactivated_at: now,
            deactivated_reason: "Account banned",
          }).eq("user_id", input.target_id).eq("is_active", true),
        ])

        await writeSecurityLog(serviceClient, {
          userId: input.target_id,
          eventType: "user_banned",
          severity: "high",
          ipAddress,
          userAgent,
          message: `User ${targetProfile.email} banned by super_admin ${profile.email}`,
          metadata: { admin_id: user.id, reason: input.notes },
        })

        result = { user_id: input.target_id, banned: true, banned_at: now }
        break
      }

      // ── Unban user ─────────────────────────────────────────────────────────
      case "unban_user": {
        requireSuperAdmin(profile)

        const { data: targetProfile } = await serviceClient
          .from("profiles")
          .select("id, is_banned, email")
          .eq("id", input.target_id)
          .single()

        if (!targetProfile) throw Errors.notFound("User not found")
        if (!targetProfile.is_banned) {
          throw Errors.conflict("User is not currently banned")
        }

        await serviceClient.from("profiles").update({
          is_banned: false,
          ban_reason: null,
          banned_at: null,
          banned_by: null,
        }).eq("id", input.target_id)

        await writeSecurityLog(serviceClient, {
          userId: input.target_id,
          eventType: "user_unbanned",
          severity: "medium",
          ipAddress,
          userAgent,
          message: `User ${targetProfile.email} unbanned by super_admin ${profile.email}`,
          metadata: { admin_id: user.id, notes: input.notes },
        })

        result = { user_id: input.target_id, unbanned: true }
        break
      }

      // ── Global pause (placeholder) ─────────────────────────────────────────
      case "global_pause_placeholder": {
        requireSuperAdmin(profile)

        // TODO(global-circuit-breaker): Implement platform-wide trading halt.
        // This should:
        //   1. Set a platform_config flag: global_trading_paused = true
        //   2. Pause all active bots across all users
        //   3. Broadcast a system_update notification to all active users
        //   4. Trigger a critical security_log entry
        // Requires a platform_config table (add in a future migration).
        console.warn("[GLOBAL PAUSE] Placeholder invoked — not yet implemented")

        await writeSecurityLog(serviceClient, {
          userId: user.id,
          eventType: "global_pause_attempted",
          severity: "critical",
          ipAddress,
          userAgent,
          message:
            "Global trading pause invoked by super_admin — feature not yet implemented",
          metadata: { admin_id: user.id, notes: input.notes },
        })

        result = {
          message:
            "Global pause is not yet fully implemented. The attempt has been logged.",
        }
        break
      }

      default:
        throw Errors.badRequest("Unknown admin action")
    }

    // ── 4. Audit log for all admin actions ────────────────────────────────────
    await writeAuditLog(serviceClient, {
      userId: user.id,
      actorRole: profile.role,
      action: `ADMIN_${input.action.toUpperCase()}`,
      recordId: input.target_id,
      ipAddress,
      userAgent,
      source: "admin_dashboard",
      metadata: { notes: input.notes, result },
    })

    return jsonResponse(req, {
      action: input.action,
      target_id: input.target_id,
      performed_at: now,
      performed_by: user.id,
      ...result,
    })
  }),
)
