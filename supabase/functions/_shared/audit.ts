import { SupabaseClient } from "@supabase/supabase-js"
import { AuditLogParams, SecurityLogParams } from "./types.ts"

// Writes a row to audit_logs using the service client (bypasses RLS).
// Failures are logged to stderr but do NOT throw — a failing audit write
// must never roll back a successful user action, but it must be visible
// in function logs for investigation.
export async function writeAuditLog(
  serviceClient: SupabaseClient,
  params: AuditLogParams,
): Promise<void> {
  const { error } = await serviceClient.from("audit_logs").insert({
    user_id: params.userId,
    actor_role: params.actorRole ?? null,
    action: params.action,
    table_name: params.tableName ?? null,
    record_id: params.recordId ?? null,
    old_values: params.oldValues ?? null,
    new_values: params.newValues ?? null,
    ip_address: params.ipAddress ?? null,
    user_agent: params.userAgent ?? null,
    source: params.source ?? "edge_function",
    session_id: params.sessionId ?? null,
    metadata: params.metadata ?? {},
  })

  if (error) {
    console.error("[AUDIT] Write failed:", JSON.stringify(error))
  }
}

// Writes a row to security_logs using the service client.
// Same non-throwing contract as writeAuditLog.
export async function writeSecurityLog(
  serviceClient: SupabaseClient,
  params: SecurityLogParams,
): Promise<void> {
  const { error } = await serviceClient.from("security_logs").insert({
    user_id: params.userId ?? null,
    event_type: params.eventType,
    severity: params.severity,
    source: params.source ?? "edge_function",
    ip_address: params.ipAddress ?? null,
    user_agent: params.userAgent ?? null,
    message: params.message,
    metadata: params.metadata ?? {},
  })

  if (error) {
    console.error("[SECURITY_LOG] Write failed:", JSON.stringify(error))
  }
}
