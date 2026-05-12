/**
 * Admin app middleware.
 *
 *   1. Refresh Supabase session (auth.getUser validates JWT).
 *   2. Block unauthenticated users from /(admin) — redirect to /sign-in.
 *   3. Block non-admin users with a 404 (don't leak the existence of the
 *      admin app to a logged-in customer).
 *   4. Edge Functions independently re-verify admin role server-side.
 *
 * SECURITY: role lives in user.app_metadata.role (server-only writable).
 * NEVER trust user.user_metadata for authorization decisions.
 */
import { NextResponse, type NextRequest } from "next/server";

import { updateSession } from "@ta/supabase/middleware";

const PUBLIC_AUTH_PATHS  = ["/sign-in"];
const AUTH_CALLBACK_PATH = "/auth/callback";

function isPublicAuthPath(pathname: string): boolean {
  if (pathname.startsWith(AUTH_CALLBACK_PATH)) return true;
  return PUBLIC_AUTH_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

export async function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const { response, userId, role } = await updateSession(request);

  // Unauthenticated → /sign-in
  if (!userId && !isPublicAuthPath(pathname)) {
    const url = request.nextUrl.clone();
    url.pathname = "/sign-in";
    url.searchParams.set("next", `${pathname}${search}`);
    return NextResponse.redirect(url);
  }

  // Authenticated but not admin → 404 (don't leak admin app existence).
  if (userId && role !== "admin" && !isPublicAuthPath(pathname)) {
    return new NextResponse("Not found", { status: 404 });
  }

  // Authenticated admin on public auth flow → bounce to overview.
  if (userId && role === "admin" && isPublicAuthPath(pathname)
      && !pathname.startsWith(AUTH_CALLBACK_PATH)) {
    const url = request.nextUrl.clone();
    url.pathname = "/overview";
    url.search = "";
    return NextResponse.redirect(url);
  }

  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)"],
};
