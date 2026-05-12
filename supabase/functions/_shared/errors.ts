// Central error type used by all Edge Functions.
// HTTP status and optional machine-readable code are carried in the error
// so the top-level handler can produce a well-formed JSON error response.

export class HttpError extends Error {
  constructor(
    public override message: string,
    public readonly status: number,
    public readonly code?: string,
  ) {
    super(message)
    this.name = "HttpError"
    Object.setPrototypeOf(this, HttpError.prototype)
  }
}

// Convenience factories for common HTTP errors.
export const Errors = {
  unauthorized: (msg = "Unauthorized") => new HttpError(msg, 401, "UNAUTHORIZED"),
  forbidden: (msg = "Forbidden") => new HttpError(msg, 403, "FORBIDDEN"),
  notFound: (msg = "Not found") => new HttpError(msg, 404, "NOT_FOUND"),
  badRequest: (msg: string) => new HttpError(msg, 400, "BAD_REQUEST"),
  unprocessable: (msg: string) => new HttpError(msg, 422, "VALIDATION_ERROR"),
  conflict: (msg: string) => new HttpError(msg, 409, "CONFLICT"),
  tooManyRequests: (msg = "Rate limit exceeded") =>
    new HttpError(msg, 429, "RATE_LIMITED"),
  internal: (msg = "Internal server error") =>
    new HttpError(msg, 500, "INTERNAL_ERROR"),
} as const
