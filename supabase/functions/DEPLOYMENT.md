# Edge Functions — Deployment Guide

## Prerequisites

```bash
npm install -g supabase
supabase login
supabase link --project-ref <your-project-ref>
```

---

## Setting Secrets

Set all secrets before deploying. Secrets are encrypted at rest by Supabase.

```bash
# Required for all functions
supabase secrets set SUPABASE_URL=https://<project-ref>.supabase.co
supabase secrets set SUPABASE_ANON_KEY=eyJ...
supabase secrets set SUPABASE_SERVICE_ROLE_KEY=eyJ...

# API key encryption secret (32+ random bytes)
supabase secrets set API_KEY_ENCRYPTION_SECRET=$(openssl rand -base64 32)

# CORS allowed origins
supabase secrets set ALLOWED_ORIGINS="https://ornek.com,https://musteri.ornek.com,https://admin.ornek.com"

# Stripe (deploy stripe-webhook after setting these)
supabase secrets set STRIPE_SECRET_KEY=sk_live_...
supabase secrets set STRIPE_WEBHOOK_SECRET=whsec_...
```

Verify secrets are set:
```bash
supabase secrets list
```

---

## Deploying Functions

Deploy all functions at once:
```bash
supabase functions deploy
```

Deploy individual functions:
```bash
supabase functions deploy store-exchange-api-key
supabase functions deploy revoke-exchange-api-key
supabase functions deploy manual-trade-approval
supabase functions deploy create-manual-signal
supabase functions deploy bot-control
supabase functions deploy exchange-health-check
supabase functions deploy create-notification
supabase functions deploy admin-security-action

# stripe-webhook MUST be deployed with --no-verify-jwt
# because Stripe sends webhooks without a user JWT.
supabase functions deploy stripe-webhook --no-verify-jwt
```

---

## Local Development

```bash
# Start local Supabase stack (runs migrations automatically)
supabase start

# Serve all functions locally with env vars from .env file
cp supabase/functions/.env.example supabase/functions/.env
# Edit .env with your local values, then:
supabase functions serve --env-file supabase/functions/.env

# Test a function
curl -i --location --request POST \
  'http://localhost:54321/functions/v1/bot-control' \
  --header 'Authorization: Bearer <user-jwt>' \
  --header 'Content-Type: application/json' \
  --data '{"bot_id":"<uuid>","action":"pause"}'

# Test stripe-webhook locally using Stripe CLI
stripe listen --forward-to localhost:54321/functions/v1/stripe-webhook
stripe trigger customer.subscription.created
```

---

## Production URLs

After deployment, functions are available at:
```
https://<project-ref>.supabase.co/functions/v1/store-exchange-api-key
https://<project-ref>.supabase.co/functions/v1/revoke-exchange-api-key
https://<project-ref>.supabase.co/functions/v1/manual-trade-approval
https://<project-ref>.supabase.co/functions/v1/create-manual-signal
https://<project-ref>.supabase.co/functions/v1/bot-control
https://<project-ref>.supabase.co/functions/v1/exchange-health-check
https://<project-ref>.supabase.co/functions/v1/admin-security-action
https://<project-ref>.supabase.co/functions/v1/create-notification
https://<project-ref>.supabase.co/functions/v1/stripe-webhook
```

Register the stripe-webhook URL in your Stripe Dashboard:
  Developers → Webhooks → Add endpoint → paste the stripe-webhook URL

---

## Supabase Dashboard: disable encrypted_api_keys table

After deploying, go to:
  Supabase Dashboard → API → Tables → encrypted_api_keys → disable Data API access

This ensures no client (even with a valid JWT) can reach the table via PostgREST.
The RLS deny-all policy is the primary guard; disabling the API adds a second layer.
