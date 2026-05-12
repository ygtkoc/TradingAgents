import type { AppUser, UserRole } from "@ta/types";

/** UI-side role check. Backend always re-verifies; this is for UI gating only. */
export function hasRole(user: AppUser | null | undefined, role: UserRole): boolean {
  return !!user && user.role === role;
}

export const isAdmin = (user: AppUser | null | undefined): boolean => hasRole(user, "admin");
