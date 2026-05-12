import { createClient, SupabaseClient } from "@supabase/supabase-js"
import {
  SUPABASE_ANON_KEY,
  SUPABASE_SERVICE_ROLE_KEY,
  SUPABASE_URL,
} from "./config.ts"

// Creates a Supabase client scoped to the user's JWT.
// RLS policies apply — this client sees only what the user is allowed to see.
// Use for reading user-accessible data and for auth.getUser().
export function createSupabaseUserClient(req: Request): SupabaseClient {
  const authHeader = req.headers.get("Authorization") ?? ""
  return createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    global: { headers: { Authorization: authHeader } },
    auth: { persistSession: false, autoRefreshToken: false },
  })
}

// Creates a Supabase client with the service_role key.
// This client BYPASSES ALL RLS POLICIES.
//
// Rules:
//   1. Never return this client or its key to any client-facing code or response.
//   2. Only use it for writes that must bypass RLS (pipeline tables, audit logs).
//   3. Always pair service_role writes with explicit ownership checks
//      performed beforehand using the user client or the service client.
export function createSupabaseServiceClient(): SupabaseClient {
  return createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, {
    auth: { persistSession: false, autoRefreshToken: false },
  })
}
