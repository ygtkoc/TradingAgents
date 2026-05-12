// ── Environment variable access ─────────────────────────────────────────────
// Throws at boot time if a required secret is absent, so a misconfigured
// deployment fails loudly rather than at first user request.

function required(name: string): string {
  const val = Deno.env.get(name)
  if (!val) throw new Error(`Missing required environment variable: ${name}`)
  return val
}

function optional(name: string, fallback = ""): string {
  return Deno.env.get(name) ?? fallback
}

export const SUPABASE_URL = required("SUPABASE_URL")
export const SUPABASE_ANON_KEY = required("SUPABASE_ANON_KEY")

// NEVER expose this to any client-facing code or response.
export const SUPABASE_SERVICE_ROLE_KEY = required("SUPABASE_SERVICE_ROLE_KEY")

// 32+ byte random secret used for AES-256-GCM encryption of API key payloads.
// TODO(production): replace with Supabase Vault (pgsodium) key references
// so the encryption key is managed by the KMS and never lives in env vars.
export const API_KEY_ENCRYPTION_SECRET = required("API_KEY_ENCRYPTION_SECRET")

// Stripe — only required when stripe-webhook function is deployed.
export const STRIPE_SECRET_KEY = optional("STRIPE_SECRET_KEY")
export const STRIPE_WEBHOOK_SECRET = optional("STRIPE_WEBHOOK_SECRET")

// Comma-separated list of allowed CORS origins.
// Example: https://ornek.com,https://musteri.ornek.com,https://admin.ornek.com
const rawOrigins = optional(
  "ALLOWED_ORIGINS",
  "http://localhost:3000,http://localhost:3001"
)
export const ALLOWED_ORIGINS: ReadonlySet<string> = new Set(
  rawOrigins.split(",").map((o) => o.trim()).filter(Boolean)
)
