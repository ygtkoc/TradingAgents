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

  const authResult = await withTimeout(
    updateSession(request),
    3500,
    "customer auth middleware timed out",
  );

  if (!authResult) {
    const url = request.nextUrl.clone();
    url.pathname = "/sign-in";
    url.searchParams.set("next", `${pathname}${search}`);
    url.searchParams.set("error", "auth_timeout");
    return NextResponse.redirect(url);
  }

  const { response, userId } = authResult;
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

async function withTimeout<T>(promise: Promise<T>, ms: number, label: string): Promise<T | null> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      promise,
      new Promise<null>((resolve) => {
        timer = setTimeout(() => {
          console.warn(label);
          resolve(null);
        }, ms);
      }),
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}
