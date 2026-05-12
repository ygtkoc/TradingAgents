/**
 * Server-side Supabase client for RSC + Route Handlers + Server Actions.
 *
 * Reads + writes the auth cookie via Next's `cookies()` helper. Always
 * authenticates with the user's anon session — NEVER service-role.
 *
 * IMPORTANT: this client must be created PER-REQUEST (no singleton).
 */
import { cookies } from "next/headers";

import { env } from "@ta/config/env";
import type { Database } from "@ta/types/database";
import { createServerClient as _createServerClient, type CookieOptions } from "@supabase/ssr";

export function createServerClient() {
  const cookieStore = cookies();

  return _createServerClient<Database>(
    env.NEXT_PUBLIC_SUPABASE_URL,
    env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
    {
      cookies: {
        get(name: string) {
          return cookieStore.get(name)?.value;
        },
        set(name: string, value: string, options: CookieOptions) {
          // RSC contexts cannot mutate cookies; setting will throw and is caught.
          try {
            cookieStore.set({ name, value, ...options });
          } catch {
            // no-op in RSC; middleware handles refresh.
          }
        },
        remove(name: string, options: CookieOptions) {
          try {
            cookieStore.set({ name, value: "", ...options });
          } catch {
            // no-op in RSC.
          }
        },
      },
    },
  );
}
