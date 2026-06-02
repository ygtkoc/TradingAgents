/**
 * Customer app middleware.
 *
 * Keep this path fast. Vercel Edge middleware has a strict execution budget;
 * slow external auth validation should degrade to a controlled redirect, not a
 * customer-facing 504.
 */
import { isDemoMode } from "@ta/config/env";
import { updateSession } from "@ta/supabase/middleware";
import { NextResponse, type NextRequest } from "next/server";

const PUBLIC_AUTH_PATHS = ["/sign-in", "/sign-up", "/reset-password", "/verify-email"];
const AUTH_CALLBACK_PATH = "/auth/callback";

function isPublicAuthPath(pathname: string): boolean {
  if (pathname.startsWith(AUTH_CALLBACK_PATH)) return true;
  return PUBLIC_AUTH_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

export async function middleware(request: NextRequest) {
  if (isDemoMode) {
    return NextResponse.next({ request: { headers: request.headers } });
  }

  const { pathname, search } = request.nextUrl;

  // Public auth routes should not make a network call in middleware. Sign-in
  // itself can handle the client-side auth state after load.
  if (isPublicAuthPath(pathname)) {
    return NextResponse.next({ request: { headers: request.headers } });
  }

  if (!hasSupabaseAuthCookie(request)) {
    const url = request.nextUrl.clone();
    url.pathname = "/sign-in";
    url.searchParams.set("next", `${pathname}${search}`);
    return NextResponse.redirect(url);
  }

  const { response, userId } = await updateSession(request);
  if (!userId) {
    const url = request.nextUrl.clone();
    url.pathname = "/sign-in";
    url.searchParams.set("next", `${pathname}${search}`);
    return NextResponse.redirect(url);
  }

  return response;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|robots.txt|manifest.webmanifest|sw.js|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)",
  ],
};

function hasSupabaseAuthCookie(request: NextRequest): boolean {
  return request.cookies
    .getAll()
    .some((cookie) => cookie.name.startsWith("sb-") && cookie.name.includes("auth-token"));
}
