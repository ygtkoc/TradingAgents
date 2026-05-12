import { SupabaseClient, User } from "@supabase/supabase-js"
import { Errors } from "./errors.ts"
import { Profile, UserRole } from "./types.ts"

const ADMIN_ROLES: ReadonlySet<UserRole> = new Set([
  "admin",
  "super_admin",
  "security_admin",
])

// Resolves the user from the Authorization header JWT.
// Uses the user-scoped client (RLS applies) so Supabase verifies
// signature + expiry + revocation status.
export async function getAuthenticatedUser(
  userClient: SupabaseClient,
): Promise<User> {
  const { data: { user }, error } = await userClient.auth.getUser()
  if (error || !user) throw Errors.unauthorized("Invalid or expired session")
  return user
}

// Fetches the user's profile via the service client (to bypass RLS on profiles
// and avoid the SECURITY DEFINER function overhead in hot paths).
// Throws 403 if the account is banned.
export async function getUserProfile(
  serviceClient: SupabaseClient,
  userId: string,
): Promise<Profile> {
  const { data, error } = await serviceClient
    .from("profiles")
    .select("id, email, role, is_banned, subscription_status, risk_level, two_factor_enabled")
    .eq("id", userId)
    .single()

  if (error || !data) throw Errors.notFound("User profile not found")
  if ((data as Profile).is_banned) {
    throw Errors.forbidden("Your account has been suspended. Contact support.")
  }
  return data as Profile
}

// Fetches user settings (paper/live trading flags, risk defaults).
export async function getUserSettings(
  serviceClient: SupabaseClient,
  userId: string,
) {
  const { data, error } = await serviceClient
    .from("user_settings")
    .select("*")
    .eq("user_id", userId)
    .single()

  if (error || !data) throw Errors.notFound("User settings not found")
  return data
}

// Fetches the user's active subscription.
export async function getUserSubscription(
  serviceClient: SupabaseClient,
  userId: string,
) {
  const { data, error } = await serviceClient
    .from("subscriptions")
    .select("*")
    .eq("user_id", userId)
    .single()

  if (error || !data) return null
  return data
}

// Role guards — throw HttpError 403 if the role requirement is not met.

export function requireAdmin(profile: Profile): void {
  if (!ADMIN_ROLES.has(profile.role)) {
    throw Errors.forbidden("Admin access required")
  }
}

export function requireSuperAdmin(profile: Profile): void {
  if (profile.role !== "super_admin") {
    throw Errors.forbidden("Super-admin access required")
  }
}

export function requireSecurityAdmin(profile: Profile): void {
  if (!["security_admin", "super_admin"].includes(profile.role)) {
    throw Errors.forbidden("Security-admin access required")
  }
}
