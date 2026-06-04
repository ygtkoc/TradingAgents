import { NextResponse, type NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  const { searchParams, origin } = request.nextUrl;
  const next = safeNext(searchParams.get("next"));
  const error = safeError(searchParams.get("error"));
  const redirectUrl = new URL("/sign-in", origin);

  redirectUrl.searchParams.set("next", next);
  if (error) {
    redirectUrl.searchParams.set("error", error);
  }

  const response = NextResponse.redirect(redirectUrl);
  for (const cookie of request.cookies.getAll()) {
    if (cookie.name.startsWith("sb-")) {
      response.cookies.delete(cookie.name);
    }
  }

  return response;
}

function safeNext(value: string | null) {
  if (value?.startsWith("/") && !value.startsWith("//")) {
    return value;
  }

  return "/dashboard";
}

function safeError(value: string | null) {
  if (value === "session_expired" || value === "auth_retryable") {
    return value;
  }

  return null;
}
