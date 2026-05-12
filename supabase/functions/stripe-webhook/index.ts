// [EF-STRIPE-01] stripe-webhook
//
// Public endpoint — no user JWT required.
// Stripe calls this directly; authentication is ONLY the Stripe-Signature header.
//
// IMPORTANT: This function must be deployed with --no-verify-jwt flag:
//   supabase functions deploy stripe-webhook --no-verify-jwt
//
// Handles:
//   customer.subscription.created  → upsert subscription, update profile
//   customer.subscription.updated  → upsert subscription, update profile
//   customer.subscription.deleted  → cancel subscription, update profile
//   invoice.payment_succeeded       → insert payment record
//   invoice.payment_failed          → insert payment record, update subscription

import Stripe from "stripe"
import { writeAuditLog } from "../_shared/audit.ts"
import { Errors } from "../_shared/errors.ts"
import { jsonResponse, withErrorHandler } from "../_shared/response.ts"
import { createSupabaseServiceClient } from "../_shared/supabase.ts"
import {
  STRIPE_SECRET_KEY,
  STRIPE_WEBHOOK_SECRET,
} from "../_shared/config.ts"

const stripe = new Stripe(STRIPE_SECRET_KEY, {
  apiVersion: "2023-10-16",
  httpClient: Stripe.createFetchHttpClient(),
})

const cryptoProvider = Stripe.createSubtleCryptoProvider()

Deno.serve((req: Request) =>
  withErrorHandler(req, async () => {
    if (req.method !== "POST") throw Errors.badRequest("Method not allowed")

    // ── 1. Signature verification ─────────────────────────────────────────────
    // Body must be read as raw text BEFORE parsing for signature to be valid.
    const body = await req.text()
    const signature = req.headers.get("stripe-signature")

    if (!signature) {
      throw Errors.unauthorized("Missing Stripe-Signature header")
    }

    let event: Stripe.Event
    try {
      event = await stripe.webhooks.constructEventAsync(
        body,
        signature,
        STRIPE_WEBHOOK_SECRET,
        undefined,
        cryptoProvider,
      )
    } catch (err) {
      console.error("[STRIPE] Signature verification failed:", err)
      throw Errors.unauthorized("Invalid Stripe signature")
    }

    console.log(`[STRIPE] Processing event: ${event.type} (${event.id})`)

    const serviceClient = createSupabaseServiceClient()

    // ── 2. Event routing ──────────────────────────────────────────────────────
    switch (event.type) {
      case "customer.subscription.created":
      case "customer.subscription.updated": {
        const sub = event.data.object as Stripe.Subscription
        await handleSubscriptionUpsert(serviceClient, sub, event.type)
        break
      }

      case "customer.subscription.deleted": {
        const sub = event.data.object as Stripe.Subscription
        await handleSubscriptionDeleted(serviceClient, sub)
        break
      }

      case "invoice.payment_succeeded": {
        const invoice = event.data.object as Stripe.Invoice
        await handlePaymentSucceeded(serviceClient, invoice)
        break
      }

      case "invoice.payment_failed": {
        const invoice = event.data.object as Stripe.Invoice
        await handlePaymentFailed(serviceClient, invoice)
        break
      }

      default:
        // Unknown event types are silently ignored but logged.
        console.log(`[STRIPE] Unhandled event type: ${event.type}`)
    }

    // Stripe requires a 2xx response within 30 seconds.
    return jsonResponse(req, { received: true })
  }),
)

// ── Handler: subscription created/updated ────────────────────────────────────

async function handleSubscriptionUpsert(
  serviceClient: ReturnType<typeof createSupabaseServiceClient>,
  sub: Stripe.Subscription,
  eventType: string,
): Promise<void> {
  const customerId = sub.customer as string

  // Look up the user by stripe_customer_id.
  const { data: existingSub } = await serviceClient
    .from("subscriptions")
    .select("id, user_id")
    .eq("stripe_customer_id", customerId)
    .single()

  if (!existingSub) {
    // First-time subscription for this customer — try to match via email.
    // This handles the case where the customer was created in Stripe first.
    console.warn(
      `[STRIPE] No subscription record found for customer ${customerId}. ` +
      "Attempting customer email lookup.",
    )

    let customer: Stripe.Customer | Stripe.DeletedCustomer
    try {
      customer = await stripe.customers.retrieve(customerId)
    } catch {
      console.error(`[STRIPE] Could not retrieve customer ${customerId}`)
      return
    }

    if (customer.deleted || !("email" in customer) || !customer.email) {
      console.error(`[STRIPE] Customer ${customerId} has no email`)
      return
    }

    const { data: profile } = await serviceClient
      .from("profiles")
      .select("id")
      .eq("email", customer.email)
      .single()

    if (!profile) {
      console.error(
        `[STRIPE] No profile found for customer email ${customer.email}`,
      )
      return
    }

    await upsertSubscriptionRecord(serviceClient, profile.id, customerId, sub)
    return
  }

  await upsertSubscriptionRecord(
    serviceClient,
    existingSub.user_id,
    customerId,
    sub,
  )

  await writeAuditLog(serviceClient, {
    userId: existingSub.user_id,
    actorRole: null,
    action: eventType === "customer.subscription.created"
      ? "SUBSCRIPTION_CREATED"
      : "SUBSCRIPTION_UPDATED",
    tableName: "subscriptions",
    recordId: existingSub.id,
    source: "stripe_webhook",
    metadata: { stripe_subscription_id: sub.id, status: sub.status },
  })
}

async function upsertSubscriptionRecord(
  serviceClient: ReturnType<typeof createSupabaseServiceClient>,
  userId: string,
  stripeCustomerId: string,
  sub: Stripe.Subscription,
): Promise<void> {
  const plan = resolvePlanFromSubscription(sub)
  const limits = getPlanLimits(plan)

  const { error } = await serviceClient.from("subscriptions").upsert(
    {
      user_id: userId,
      stripe_customer_id: stripeCustomerId,
      stripe_subscription_id: sub.id,
      plan,
      status: sub.status,
      current_period_start: new Date(
        sub.current_period_start * 1000,
      ).toISOString(),
      current_period_end: new Date(sub.current_period_end * 1000).toISOString(),
      trial_end: sub.trial_end
        ? new Date(sub.trial_end * 1000).toISOString()
        : null,
      cancelled_at: sub.canceled_at
        ? new Date(sub.canceled_at * 1000).toISOString()
        : null,
      ...limits,
    },
    { onConflict: "user_id" },
  )

  if (error) {
    console.error("[STRIPE] Failed to upsert subscription:", error)
    return
  }

  // Keep profiles.subscription_status in sync.
  await serviceClient.from("profiles").update({
    subscription_status: mapStripeStatusToEnum(sub.status),
  }).eq("id", userId)
}

// ── Handler: subscription deleted ────────────────────────────────────────────

async function handleSubscriptionDeleted(
  serviceClient: ReturnType<typeof createSupabaseServiceClient>,
  sub: Stripe.Subscription,
): Promise<void> {
  const { data: existing } = await serviceClient
    .from("subscriptions")
    .select("id, user_id")
    .eq("stripe_subscription_id", sub.id)
    .single()

  if (!existing) return

  await serviceClient.from("subscriptions").update({
    status: "cancelled",
    cancelled_at: new Date().toISOString(),
    real_trading_allowed: false,
  }).eq("id", existing.id)

  await serviceClient.from("profiles").update({
    subscription_status: "cancelled",
  }).eq("id", existing.user_id)

  await writeAuditLog(serviceClient, {
    userId: existing.user_id,
    actorRole: null,
    action: "SUBSCRIPTION_CANCELLED",
    tableName: "subscriptions",
    recordId: existing.id,
    source: "stripe_webhook",
    metadata: { stripe_subscription_id: sub.id },
  })
}

// ── Handler: payment succeeded ────────────────────────────────────────────────

async function handlePaymentSucceeded(
  serviceClient: ReturnType<typeof createSupabaseServiceClient>,
  invoice: Stripe.Invoice,
): Promise<void> {
  if (!invoice.payment_intent || !invoice.customer) return

  const customerId = invoice.customer as string

  const { data: sub } = await serviceClient
    .from("subscriptions")
    .select("id, user_id")
    .eq("stripe_customer_id", customerId)
    .single()

  const { error } = await serviceClient.from("payments").insert({
    user_id: sub?.user_id ?? null,
    subscription_id: sub?.id ?? null,
    stripe_payment_id: invoice.payment_intent as string,
    stripe_invoice_id: invoice.id,
    amount: invoice.amount_paid,
    currency: invoice.currency,
    status: "succeeded",
    description: invoice.description ?? "Subscription payment",
    paid_at: new Date().toISOString(),
    metadata: { stripe_invoice_id: invoice.id },
  })

  if (error) {
    console.error("[STRIPE] Failed to insert payment record:", error)
  }

  if (sub) {
    // Ensure subscription status is active after successful payment.
    await serviceClient.from("subscriptions").update({
      status: "active",
    }).eq("id", sub.id)

    await serviceClient.from("profiles").update({
      subscription_status: "active",
    }).eq("id", sub.user_id)
  }
}

// ── Handler: payment failed ────────────────────────────────────────────────────

async function handlePaymentFailed(
  serviceClient: ReturnType<typeof createSupabaseServiceClient>,
  invoice: Stripe.Invoice,
): Promise<void> {
  if (!invoice.customer) return

  const customerId = invoice.customer as string

  const { data: sub } = await serviceClient
    .from("subscriptions")
    .select("id, user_id")
    .eq("stripe_customer_id", customerId)
    .single()

  await serviceClient.from("payments").insert({
    user_id: sub?.user_id ?? null,
    subscription_id: sub?.id ?? null,
    stripe_payment_id: (invoice.payment_intent as string) ?? `inv_failed_${invoice.id}`,
    stripe_invoice_id: invoice.id,
    amount: invoice.amount_due,
    currency: invoice.currency,
    status: "failed",
    failure_reason: "Stripe payment failed",
    metadata: { stripe_invoice_id: invoice.id },
  })

  if (sub) {
    await serviceClient.from("subscriptions").update({
      status: "past_due",
    }).eq("id", sub.id)

    await serviceClient.from("profiles").update({
      subscription_status: "past_due",
    }).eq("id", sub.user_id)

    await writeAuditLog(serviceClient, {
      userId: sub.user_id,
      actorRole: null,
      action: "PAYMENT_FAILED",
      tableName: "payments",
      source: "stripe_webhook",
      metadata: { stripe_invoice_id: invoice.id, amount_due: invoice.amount_due },
    })
  }
}

// ── Utilities ─────────────────────────────────────────────────────────────────

function resolvePlanFromSubscription(sub: Stripe.Subscription): string {
  // TODO: Map Stripe price IDs to internal plan names via PRICE_ID env vars.
  // For now, derive from metadata or product name.
  const metadata = sub.metadata ?? {}
  if (metadata.plan) return metadata.plan

  // Fallback: examine item price nickname.
  const nickname = sub.items.data[0]?.price?.nickname?.toLowerCase() ?? ""
  if (nickname.includes("enterprise")) return "enterprise"
  if (nickname.includes("pro")) return "pro"
  if (nickname.includes("starter")) return "starter"
  return "starter"
}

function getPlanLimits(plan: string): Record<string, unknown> {
  // TODO: Move plan limits to a database table (plan_limits) so they
  // can be changed without redeploying Edge Functions.
  const limits: Record<string, Record<string, unknown>> = {
    free: {
      max_bots: 1,
      max_trades_per_day: 10,
      real_trading_allowed: false,
      api_calls_per_day: 500,
    },
    starter: {
      max_bots: 3,
      max_trades_per_day: 50,
      real_trading_allowed: false,
      api_calls_per_day: 2000,
    },
    pro: {
      max_bots: 10,
      max_trades_per_day: 500,
      real_trading_allowed: true,
      api_calls_per_day: 10000,
    },
    enterprise: {
      max_bots: 100,
      max_trades_per_day: 10000,
      real_trading_allowed: true,
      api_calls_per_day: 100000,
    },
  }
  return limits[plan] ?? limits.starter
}

function mapStripeStatusToEnum(status: string): string {
  const map: Record<string, string> = {
    active: "active",
    trialing: "trialing",
    past_due: "past_due",
    canceled: "cancelled",
    unpaid: "unpaid",
    paused: "paused",
    incomplete: "past_due",
    incomplete_expired: "cancelled",
  }
  return map[status] ?? "cancelled"
}
