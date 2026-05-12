/**
 * Middleware-friendly Supabase helpers.
 *
 * `updateSession` MUST be called from each app's middleware. It validates
 * the JWT (auth.getUser), refreshes the cookie, and propagates Set-Cookie
 * to the outgoing response.
 *
 * Returns the user (if any) and the patched response so the caller can do
 * role-based gating.
 */
import { NextResponse, type NextRequest } from "next/server";

import { env } from "@ta/config/env";
import type { Database } from "@ta/types/database";
import type { UserRole } from "@ta/types/enums";
import { createServerClient as _createServerClient, type CookieOptions } from "@supabase/ssr";

export interface UpdateSessionResult {
  response: NextResponse;
  userId:   string | null;
  email:    string | null;
  role:     UserRole;
}

export async function updateSession(request: NextRequest): Promise<UpdateSessionResult> {
  let response = NextResponse.next({ request: { headers: request.headers } });

  const supabase = _createServerClient<Database>(
    env.NEXT_PUBLIC_SUPABASE_URL,
    env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
    {
      cookies: {
        get(name: string) {
          return request.cookies.get(name)?.value;
        },
        set(name: string, value: string, options: CookieOptions) {
          request.cookies.set({ name, value, ...options });
          response = NextResponse.next({ request: { headers: request.headers } });
          response.cookies.set({ name, value, ...options });
        },
        remove(name: string, options: CookieOptions) {
          request.cookies.set({ name, value: "", ...options });
          response = NextResponse.next({ request: { headers: request.headers } });
          response.cookies.set({ name, value: "", ...options });
        },
      },
    },
  );

  // CRITICAL: `getUser()` validates the JWT against Supabase. `getSession()`
  // only reads the local cookie and is NOT trustworthy for gating.
  const { data: { user } } = await supabase.auth.getUser();

  // role lives in app_metadata (server-only writable). Default to "user".
  const rawRole = (user?.app_metadata?.role as string | undefined) ?? "user";
  const role: UserRole = rawRole === "admin" ? "admin" : "user";

  return {
    response,
    userId: user?.id ?? null,
    email:  user?.email ?? null,
    role,
  };
}
