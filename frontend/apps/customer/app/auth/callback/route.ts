import { NextResponse, type NextRequest } from "next/server";

import { createServerClient } from "@ta/supabase/server";

/**
 * Supabase Auth callback handler.
 *
 * Handles:
 *   - email confirmation links  (?token_hash=...&type=signup|email_change)
 *   - password reset links      (?type=recovery)
 *   - OAuth provider redirects  (?code=...)
 *
 * On success → redirect to `?next=` (or /dashboard).
 * On failure → redirect to /sign-in?error=...
 */
export async function GET(request: NextRequest) {
  const { searchParams, origin } = request.nextUrl;
  const code      = searchParams.get("code");
  const tokenHash = searchParams.get("token_hash");
  const type      = searchParams.get("type") as
    | "signup" | "invite" | "magiclink" | "recovery" | "email_change" | null;
  const next      = searchParams.get("next") || "/dashboard";

  const supabase = createServerClient();

  if (code) {
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) return NextResponse.redirect(new URL(next, origin));
    return NextResponse.redirect(new URL(`/sign-in?error=${encodeURIComponent(error.message)}`, origin));
  }

  if (tokenHash && type) {
    const { error } = await supabase.auth.verifyOtp({ type, token_hash: tokenHash });
    if (!error) return NextResponse.redirect(new URL(next, origin));
    return NextResponse.redirect(new URL(`/sign-in?error=${encodeURIComponent(error.message)}`, origin));
  }

  return NextResponse.redirect(new URL("/sign-in?error=missing_code", origin));
}
