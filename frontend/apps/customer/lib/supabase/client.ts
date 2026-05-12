/**
 * Browser-side Supabase singleton wrapper used by client-component hooks.
 * Server hooks import @ta/supabase/server directly.
 */
import { createBrowserClient } from "@ta/supabase/browser";

export const supabase = createBrowserClient();
export type SupabaseBrowserClient = typeof supabase;
