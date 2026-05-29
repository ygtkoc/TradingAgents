/**
 * Browser-side Supabase client.
 *
 * Use in client components only. Authenticates with the user's anon-key
 * session cookie (managed by @supabase/ssr). NEVER imports service-role.
 */
import { env } from "@ta/config/env";
import { createBrowserClient as _createBrowserClient } from "@supabase/ssr";

// Supabase generated database types are intentionally incomplete in this repo.
// Keep the browser client permissive so app code owns its domain types instead.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type BrowserDatabase = any;

let _client: ReturnType<typeof _createBrowserClient<BrowserDatabase>> | undefined;

export function createBrowserClient() {
  // Singleton — Supabase JS expects one client per browser context.
  if (_client) return _client;
  _client = _createBrowserClient<BrowserDatabase>(
    env.NEXT_PUBLIC_SUPABASE_URL,
    env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
  );
  return _client;
}
