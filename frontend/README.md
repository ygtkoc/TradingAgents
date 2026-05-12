# TradingAgents — Frontend Monorepo

Multi-app frontend for the TradingAgents platform. Three Next.js 14 (App Router)
apps and seven shared packages, orchestrated by Turborepo + pnpm.

| App                 | Port  | Domain                  | Purpose                       |
| ------------------- | ----- | ----------------------- | ----------------------------- |
| `apps/marketing`    | 3000  | `ornek.com`             | Public marketing site         |
| `apps/customer`     | 3001  | `musteri.ornek.com`     | Authenticated user dashboard  |
| `apps/admin`        | 3002  | `admin.ornek.com`       | Admin / operations dashboard  |

## Tech stack

- Next.js 14+ (App Router) · TypeScript · Tailwind CSS
- Supabase Auth (SSR) · `@supabase/ssr`
- TanStack React Query · Zod · `next-themes`
- Turborepo · pnpm workspaces · ESLint · Prettier

## Prerequisites

- Node.js **20+**
- pnpm **9+** (`corepack enable && corepack prepare pnpm@9.12.0 --activate`)
- A Supabase project (URL + anon key only — never the service-role key)

## Setup

```bash
# 1. Install
pnpm install

# 2. Copy env file
cp .env.example .env.local
#    Fill in NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.
#    NEVER add SUPABASE_SERVICE_ROLE_KEY here. The frontend must not see it.

# 3. Run all three apps in parallel
pnpm dev
#    marketing → http://localhost:3000
#    customer  → http://localhost:3001
#    admin     → http://localhost:3002

# Run a single app
pnpm --filter @ta/customer dev
pnpm --filter @ta/admin    dev
pnpm --filter @ta/marketing dev
```

## Scripts

```bash
pnpm dev          # all apps in parallel
pnpm build        # turbo-orchestrated builds
pnpm lint         # eslint everywhere
pnpm typecheck    # tsc --noEmit everywhere
pnpm format       # prettier write
pnpm format:check # prettier check
pnpm clean        # clear .next / .turbo / node_modules
```

## Repository layout

```
frontend/
├── apps/
│   ├── marketing/        # public site (port 3000)
│   ├── customer/         # user dashboard (port 3001)
│   └── admin/            # admin dashboard (port 3002)
└── packages/
    ├── ui/               # shadcn-style primitives + AppShell + theme
    ├── supabase/         # browser/server/middleware Supabase clients + EF wrappers
    ├── types/            # domain types + enums + EF request/response types
    ├── schemas/          # Zod schemas (shared client/server validation)
    ├── query/            # React Query client + provider + queryKeys
    ├── utils/            # cn(), format, time, permissions
    ├── config/           # env validation, route constants, feature flags
    ├── eslint-config/    # shared ESLint configs (base / next / library)
    └── tsconfig/         # shared tsconfig presets
```

## Architecture summary

### Three apps

- **Marketing** is statically renderable, has no Supabase auth, and never
  touches user data.
- **Customer** runs `middleware.ts` that refreshes the Supabase session and
  blocks unauthenticated access to the `(app)` route group.
- **Admin** runs a stricter `middleware.ts` that additionally requires
  `app_metadata.role === "admin"` — non-admins receive a `404` rather than a
  `403` so the admin app's existence is not leaked.

### Auth

- Single source of truth: `@ta/supabase/middleware` exposes `updateSession()`.
- Always uses `auth.getUser()` (validates JWT). Never `auth.getSession()` for
  authorization decisions.
- Role lives in `auth.users.app_metadata.role` (server-only writable) — never
  `user_metadata`.
- Each Edge Function independently re-verifies the role server-side; the
  frontend's role check is UI-gating only.

### Data access

The frontend is **read-mostly**:

| Track                  | Used for                                              |
| ---------------------- | ----------------------------------------------------- |
| Direct Supabase reads  | Reading any RLS-protected table the user can access   |
| Edge Functions         | All writes to trading-critical and security tables    |

The frontend **cannot** insert or update `trades`, `trade_decisions`,
`signals`, `agent_runs`, `agent_outputs`, `risk_logs`, `security_logs`,
`audit_logs`, `trade_events`, or `platform_settings`. Three independent layers
enforce this:

1. **Database**: RLS deny-by-default for INSERT/UPDATE on these tables for the
   `authenticated` role.
2. **API**: every mutation goes through an Edge Function in the backend repo.
   The frontend exposes only typed wrappers in `@ta/supabase/edge-functions`.
3. **Build**: ESLint blocks `@ta/supabase/service-role` and direct
   `createClient` from `@supabase/supabase-js`. The service-role module body
   also throws on load.

### Realtime

Realtime is reserved for state that, if stale, would be misleading or
dangerous — open trades, pending approval queue, kill-switch banner,
notifications. Everything else uses React Query refetching.

### State management

- Server state → React Query (centralized keys in `@ta/query/keys`).
- URL state → `searchParams`.
- Form state → `react-hook-form` + Zod resolver.
- Ephemeral UI → `useState`. Cross-component shell state → small Zustand
  store (per app, added when needed).

## Adding shadcn/ui components

The UI package is shadcn-compatible. Run shadcn from the repo root targeting
`packages/ui/src/primitives/`:

```bash
# Inside packages/ui
pnpm dlx shadcn@latest add dialog
# ...then move generated file into src/primitives/ and re-export from src/index.ts
```

Use `cn()` from `@ta/utils` (already wired) for class merging. The shared
Tailwind preset in `packages/ui/tailwind.preset.cjs` defines all theme tokens
(`primary`, `success`, `warning`, etc.).

## Security checklist

- [x] No `SUPABASE_SERVICE_ROLE_KEY` referenced anywhere in the frontend.
- [x] `service-role.ts` exists as a tripwire — body throws, not in `exports` map.
- [x] ESLint `no-restricted-imports` blocks the service-role module.
- [x] ESLint blocks `createClient` from `@supabase/supabase-js`.
- [x] All trading-critical mutations are Edge Function placeholders only.
- [x] Middleware validates JWTs on every request (`auth.getUser()`).
- [x] Admin role check uses `app_metadata`, not `user_metadata`.
- [x] Admin app emits `robots: { index: false, follow: false }`.
- [x] Customer middleware redirects unauthenticated → `/sign-in`.
- [x] Admin middleware returns `404` for non-admins.

## Environment variables

See `.env.example`. Only `NEXT_PUBLIC_*` variables are valid for the frontend.

Validation runs at module import time (`packages/config/src/env.ts`). A
missing required variable throws immediately rather than failing silently
at runtime.

## Deployment

- Each app is deployed independently (separate Vercel/host project, separate
  domain). Cookies are scoped per subdomain.
- `transpilePackages` in each app's `next.config.mjs` lets Next compile the
  workspace packages directly from `src/`.

## Known TODOs (intentionally deferred)

- Auth UI (sign-in / sign-up / OAuth callback handlers).
- Database type generation: `supabase gen types typescript --project-id … >
  packages/types/src/database.ts`.
- Concrete pages (dashboard widgets, bot wizard, trade detail, admin
  reconciliation).
- DataTable, charts, bot config form, kill-switch dialog.
- Realtime channel hooks (`useRealtimeChannel`).
- Notification toast system.
- Stripe billing integration.

## Conventions

- Run shared packages directly from `src/` (no `dist/`); apps transpile them
  via `transpilePackages`.
- Use `@ta/<package>` import paths; never relative `../../packages/...`.
- Never inline React Query keys — always import from `@ta/query/keys`.
- All forms validate with Zod via `@ta/schemas`. Same schema runs in the
  Edge Function on the server side (in the backend repo).
- Mutations always send an idempotency header (`x-idempotency-key`); the
  EF wrapper in `@ta/supabase/edge-functions` does this automatically.
