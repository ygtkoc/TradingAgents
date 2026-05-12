import { getCorsHeaders } from "./cors.ts"
import { HttpError } from "./errors.ts"

export function jsonResponse(
  req: Request,
  data: unknown,
  status = 200,
): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      ...getCorsHeaders(req),
      "Content-Type": "application/json",
    },
  })
}

export function errorResponse(
  req: Request,
  message: string,
  status: number,
  code?: string,
): Response {
  return new Response(JSON.stringify({ error: message, code }), {
    status,
    headers: {
      ...getCorsHeaders(req),
      "Content-Type": "application/json",
    },
  })
}

// Top-level error handler — wraps the main handler and converts HttpError
// and unexpected throws into consistent JSON responses.
export function withErrorHandler(
  req: Request,
  handler: () => Promise<Response>,
): Promise<Response> {
  return handler().catch((err: unknown) => {
    if (err instanceof HttpError) {
      console.warn(`[HTTP ${err.status}] ${err.code ?? ""}: ${err.message}`)
      return errorResponse(req, err.message, err.status, err.code)
    }
    // Log unexpected errors with full stack for observability.
    console.error("[UNHANDLED ERROR]", err)
    return errorResponse(req, "Internal server error", 500, "INTERNAL_ERROR")
  })
}
