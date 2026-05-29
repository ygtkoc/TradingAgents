# Production Deployment

This repo has three independent Next.js frontend apps and one Supabase backend.

## Frontend domains

Use one Vercel project per app:

| App | Vercel root directory | Domain |
| --- | --- | --- |
| Marketing | `frontend/apps/marketing` | `https://YOUR_DOMAIN.com` |
| Customer | `frontend/apps/customer` | `https://musteri.YOUR_DOMAIN.com` |
| Admin | `frontend/apps/admin` | `https://admin.YOUR_DOMAIN.com` |

For each Vercel project, set:

```txt
Install Command: cd ../.. && pnpm install --frozen-lockfile
Build Command: cd ../.. && pnpm --filter APP_NAME build
```

Use these build commands:

```txt
Marketing: cd ../.. && pnpm --filter @ta/marketing build
Customer:  cd ../.. && pnpm --filter @ta/customer build
Admin:     cd ../.. && pnpm --filter @ta/admin build
```

## Frontend environment variables

Add these variables to all three Vercel projects:

```env
NEXT_PUBLIC_APP_ENV=production
NEXT_PUBLIC_SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=YOUR_SUPABASE_ANON_KEY
NEXT_PUBLIC_MARKETING_URL=https://YOUR_DOMAIN.com
NEXT_PUBLIC_CUSTOMER_URL=https://musteri.YOUR_DOMAIN.com
NEXT_PUBLIC_ADMIN_URL=https://admin.YOUR_DOMAIN.com
NEXT_PUBLIC_DEMO_MODE=false
NEXT_PUBLIC_ALLOW_DEV_DIRECT_PAPER_ACCOUNT_WRITE=false
```

Do not add `SUPABASE_SERVICE_ROLE_KEY` to any frontend project.

## DNS

In the domain provider DNS panel:

```txt
A      @        76.76.21.21
CNAME  www      cname.vercel-dns.com
CNAME  musteri  cname.vercel-dns.com
CNAME  admin    cname.vercel-dns.com
```

Then add the matching domains in Vercel:

```txt
YOUR_DOMAIN.com
www.YOUR_DOMAIN.com
musteri.YOUR_DOMAIN.com
admin.YOUR_DOMAIN.com
```

## Supabase Auth URLs

In Supabase Dashboard, set:

```txt
Site URL: https://musteri.YOUR_DOMAIN.com
```

Add redirect URLs:

```txt
https://musteri.YOUR_DOMAIN.com/auth/callback
https://admin.YOUR_DOMAIN.com/auth/callback
http://localhost:3001/auth/callback
http://localhost:3002/auth/callback
```

## Supabase database and functions

Install and login once:

```bash
npm install -g supabase
supabase login
supabase link --project-ref YOUR_PROJECT_REF
```

Apply migrations:

```bash
supabase db push
```

Set Edge Function secrets:

```bash
supabase secrets set SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
supabase secrets set SUPABASE_ANON_KEY=YOUR_SUPABASE_ANON_KEY
supabase secrets set SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_KEY
supabase secrets set API_KEY_ENCRYPTION_SECRET=YOUR_32_PLUS_CHAR_SECRET
supabase secrets set ALLOWED_ORIGINS="https://YOUR_DOMAIN.com,https://musteri.YOUR_DOMAIN.com,https://admin.YOUR_DOMAIN.com"
```

Deploy functions:

```bash
supabase functions deploy admin-security-action
supabase functions deploy bot-control
supabase functions deploy create-manual-signal
supabase functions deploy create-notification
supabase functions deploy exchange-health-check
supabase functions deploy manual-trade-approval
supabase functions deploy paper-account-create
supabase functions deploy paper-account-pause
supabase functions deploy paper-account-reset
supabase functions deploy paper-account-start
supabase functions deploy revoke-exchange-api-key
supabase functions deploy store-exchange-api-key
supabase functions deploy stripe-webhook --no-verify-jwt
```

## Local verification already performed

From `frontend/`:

```bash
pnpm build
```

The build passes for `@ta/marketing`, `@ta/customer`, and `@ta/admin`.
