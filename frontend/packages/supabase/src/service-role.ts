/**
 * ╔══════════════════════════════════════════════════════════════════════════╗
 * ║  STOP. This module MUST NEVER be imported from frontend code.            ║
 * ╠══════════════════════════════════════════════════════════════════════════╣
 * ║                                                                          ║
 * ║  Service-role keys grant unrestricted access to the entire database,    ║
 * ║  bypassing RLS. They are reserved for backend Edge Functions only.      ║
 * ║                                                                          ║
 * ║  Defense layers preventing import from frontend code:                    ║
 * ║                                                                          ║
 * ║   1. ESLint `no-restricted-imports` blocks `@ta/supabase/service-role`. ║
 * ║      See packages/eslint-config/index.cjs.                              ║
 * ║                                                                          ║
 * ║   2. This module is intentionally NOT in the package `exports` map of   ║
 * ║      packages/supabase/package.json — node/bundler resolution will      ║
 * ║      reject the path.                                                    ║
 * ║                                                                          ║
 * ║   3. The module body throws on load. Even if a bundler bypassed the     ║
 * ║      exports map, importing it would fail at runtime.                    ║
 * ║                                                                          ║
 * ║   4. No SUPABASE_SERVICE_ROLE_KEY is documented in .env.example.        ║
 * ║      It is fetched server-side only by Edge Functions in the backend    ║
 * ║      repository.                                                         ║
 * ║                                                                          ║
 * ╚══════════════════════════════════════════════════════════════════════════╝
 */

throw new Error(
  "@ta/supabase/service-role is forbidden in frontend code. " +
    "Service-role operations must run inside backend Edge Functions.",
);

export {};
