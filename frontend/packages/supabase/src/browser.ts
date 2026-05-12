/**
 * Browser-side Supabase client.
 *
 * Use in client components only. Authenticates with the user's anon-key
 * session cookie (managed by @supabase/ssr). NEVER imports service-role.
 */
import { env } from "@ta/config/env";
import type { Database } from "@ta/types/database";
import { createBrowserClient as _createBrowserClient } from "@supabase/ssr";

let _client: ReturnType<typeof _createBrowserClient<Database>> | undefined;

export function createBrowserClient() {
  // Singleton — Supabase JS expects one client per browser context.
  if (_client) return _client;
  _client = _createBrowserClient<Database>(
    env.NEXT_PUBLIC_SUPABASE_URL,
    env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
  );
  return _client;
}
