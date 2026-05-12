/**
 * Customer app middleware.
 *
 *   1. In DEMO mode → bypass auth entirely (no /sign-in redirect, no JWT
 *      validation). The shell injects a synthetic demo user.
 *   2. Otherwise:
 *      a. Refresh Supabase session on every request (auth.getUser validates JWT).
 *      b. Block unauthenticated users from the (app) shell — redirect to /sign-in.
 *      c. Redirect authenticated users away from public auth flows.
 *      d. Forward Set-Cookie so RSC sees the fresh session.
 *
 * SECURITY: NEVER trust auth.getSession() in middleware (no JWT validation).
 *           updateSession() uses auth.getUser() which validates server-side.
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
  // Demo mode short-circuit — no auth checks, no Supabase calls.
  if (isDemoMode) {
    return NextResponse.next({ request: { headers: request.headers } });
  }

  const { pathname, search } = request.nextUrl;
  const { response, userId } = await updateSession(request);

  // Unauthenticated → redirect to /sign-in unless already on a public path.
  if (!userId && !isPublicAuthPath(pathname)) {
    const url = request.nextUrl.clone();
    url.pathname = "/sign-in";
    url.searchParams.set("next", `${pathname}${search}`);
    return NextResponse.redirect(url);
  }

  // Authenticated → bounce away from public auth flow into dashboard.
  if (userId && isPublicAuthPath(pathname) && !pathname.startsWith(AUTH_CALLBACK_PATH)) {
    const url = request.nextUrl.clone();
    url.pathname = "/dashboard";
    url.search = "";
    return NextResponse.redirect(url);
  }

  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)"],
};
