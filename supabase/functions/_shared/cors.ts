import { ALLOWED_ORIGINS } from "./config.ts"

// Returns CORS headers appropriate for the request origin.
// If the origin is not in the allowlist, Access-Control-Allow-Origin is
// omitted so the browser rejects the response — we do not fall back to '*'.
export function getCorsHeaders(req: Request): HeadersInit {
  const origin = req.headers.get("Origin") ?? ""
  const allowed = ALLOWED_ORIGINS.has(origin)

  if (!allowed) {
    // Return only non-origin headers; browser will block the response.
    return {
      "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
      "Access-Control-Allow-Headers":
        "authorization, x-client-info, x-idempotency-key, apikey, content-type",
    }
  }

  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
    "Access-Control-Allow-Headers":
      "authorization, x-client-info, x-idempotency-key, apikey, content-type",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  }
}

// Returns a 204 preflight response, or null if this is not an OPTIONS request.
// Call at the top of every handler: const preflight = handleCors(req); if (preflight) return preflight
export function handleCors(req: Request): Response | null {
  if (req.method !== "OPTIONS") return null
  return new Response(null, { status: 204, headers: getCorsHeaders(req) })
}
