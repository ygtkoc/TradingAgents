/**
 * Runtime environment validation.
 *
 * Validates `process.env` once at import time using Zod. Fail-closed: if a
 * required public variable is missing, the bundle errors out at startup
 * rather than silently breaking at runtime.
 *
 * SECURITY: only NEXT_PUBLIC_* variables are accepted here. The
 * service-role key MUST NEVER be referenced from frontend code.
 */
import { z } from "zod";

const PublicEnvSchema = z.object({
  NEXT_PUBLIC_APP_ENV: z
    .enum(["development", "staging", "production"])
    .default("development"),

  NEXT_PUBLIC_SUPABASE_URL: z.string().url(),
  NEXT_PUBLIC_SUPABASE_ANON_KEY: z.string().min(20),

  NEXT_PUBLIC_MARKETING_URL: z.string().url().default("http://localhost:3000"),
  NEXT_PUBLIC_CUSTOMER_URL:  z.string().url().default("http://localhost:3001"),
  NEXT_PUBLIC_ADMIN_URL:     z.string().url().default("http://localhost:3002"),

  /**
   * Demo mode — bypasses auth and serves curated demo data without
   * contacting Supabase. Useful for visual product testing without a
   * provisioned backend.
   *
   * MUST never be enabled in production deployments. Validation here is
   * informational; deployment configuration should leave it unset.
   */
  NEXT_PUBLIC_DEMO_MODE: z
    .string()
    .optional()
    .default("false")
    .transform((v) => v === "true" || v === "1"),

  /**
   * Dev-only escape hatch — when true AND the paper-account-create Edge
   * Function is unreachable, the customer app falls back to writing the
   * paper_accounts row directly via the authenticated Supabase client.
   *
   * Requires RLS policies that permit users to insert/update their own
   * paper_accounts row (migration 0007). MUST stay false in production —
   * production uses the Edge Function so balance writes are audited and
   * idempotent.
   */
  NEXT_PUBLIC_ALLOW_DEV_DIRECT_PAPER_ACCOUNT_WRITE: z
    .string()
    .optional()
    .default("false")
    .transform((v) => v === "true" || v === "1"),
});

export type PublicEnv = z.infer<typeof PublicEnvSchema>;

function readPublicEnv(): PublicEnv {
  // Next.js inlines NEXT_PUBLIC_* at build time; access them by literal name.
  const raw = {
    NEXT_PUBLIC_APP_ENV:           process.env.NEXT_PUBLIC_APP_ENV,
    NEXT_PUBLIC_SUPABASE_URL:      process.env.NEXT_PUBLIC_SUPABASE_URL,
    NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
    NEXT_PUBLIC_MARKETING_URL:     process.env.NEXT_PUBLIC_MARKETING_URL,
    NEXT_PUBLIC_CUSTOMER_URL:      process.env.NEXT_PUBLIC_CUSTOMER_URL,
    NEXT_PUBLIC_ADMIN_URL:         process.env.NEXT_PUBLIC_ADMIN_URL,
    NEXT_PUBLIC_DEMO_MODE:         process.env.NEXT_PUBLIC_DEMO_MODE,
    NEXT_PUBLIC_ALLOW_DEV_DIRECT_PAPER_ACCOUNT_WRITE:
      process.env.NEXT_PUBLIC_ALLOW_DEV_DIRECT_PAPER_ACCOUNT_WRITE,
  };

  const parsed = PublicEnvSchema.safeParse(raw);
  if (!parsed.success) {
    const issues = parsed.error.issues
      .map((i) => `  • ${i.path.join(".")}: ${i.message}`)
      .join("\n");
    throw new Error(
      `Invalid public environment variables:\n${issues}\n\n` +
        `Copy .env.example to .env.local and fill in the values.`,
    );
  }
  return parsed.data;
}

export const env: PublicEnv = readPublicEnv();

export const isProd        = env.NEXT_PUBLIC_APP_ENV === "production";
export const isStaging     = env.NEXT_PUBLIC_APP_ENV === "staging";
export const isDevelopment = env.NEXT_PUBLIC_APP_ENV === "development";

export const isDemoMode    = env.NEXT_PUBLIC_DEMO_MODE === true;
export const allowDevDirectPaperAccountWrite =
  env.NEXT_PUBLIC_ALLOW_DEV_DIRECT_PAPER_ACCOUNT_WRITE === true;
