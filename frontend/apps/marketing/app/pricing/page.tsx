import type { Metadata } from "next";
import Link from "next/link";

import { buttonVariants } from "@ta/ui";

export const metadata: Metadata = {
  title: "Pricing",
  description:
    "Choose Lucrandos access for AI trading system monitoring, paper trading workflows, crypto decision review, and risk managed trade lifecycle tools.",
  alternates: {
    canonical: "/pricing",
  },
};

const plans = [
  {
    name: "Paper",
    price: "Start",
    description: "Follow AI trading decisions, paper positions, closed trade R results, and risk events before going live.",
  },
  {
    name: "Operator",
    price: "Scale",
    description: "Review manual approvals, monitor lifecycle automation, and control paper or exchange-connected trading workflows.",
  },
  {
    name: "Desk",
    price: "Custom",
    description: "Run Lucrandos with dedicated operations, exchange routing, audit review, and advanced risk controls.",
  },
];

function getCustomerSignInUrl() {
  const configuredUrl = process.env.NEXT_PUBLIC_CUSTOMER_URL?.replace(/\/$/, "");
  const customerUrl =
    configuredUrl && !configuredUrl.includes("localhost")
      ? configuredUrl
      : "https://customer.lucrandos.com";

  return `${customerUrl}/sign-in`;
}

export default function PricingPage() {
  const customerSignInUrl = getCustomerSignInUrl();

  return (
    <main className="min-h-screen bg-[#07090b] text-zinc-50">
      <div className="pointer-events-none fixed inset-0 bg-[linear-gradient(rgba(255,255,255,0.055)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.055)_1px,transparent_1px)] bg-[size:72px_72px] opacity-35" />
      <div className="relative mx-auto flex min-h-screen max-w-6xl flex-col px-5 py-6 sm:px-8 lg:px-10">
        <nav className="flex items-center justify-between gap-4">
          <Link href="/" className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-teal-300/35 bg-teal-300/10 text-sm font-semibold text-teal-100">
              L
            </div>
            <div>
              <div className="text-sm font-semibold text-zinc-50">lucrandos</div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-teal-200/70">AI trading OS</div>
            </div>
          </Link>
          <Link href={customerSignInUrl} className={buttonVariants({ className: "bg-teal-300 text-zinc-950 hover:bg-teal-200" })}>
            Sign in
          </Link>
        </nav>

        <section className="flex flex-1 flex-col justify-center gap-10 py-12">
          <div className="max-w-3xl space-y-5">
            <div className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-200">Pricing</div>
            <h1 className="text-5xl font-semibold leading-[0.98] tracking-[0] text-zinc-50 sm:text-6xl">
              Access for paper trading, operator control, and live AI trading workflows.
            </h1>
            <p className="max-w-2xl text-base leading-8 text-zinc-300">
              Lucrandos pricing is aligned to how much control, automation, and exchange connectivity your trading operation needs.
            </p>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            {plans.map((plan) => (
              <article key={plan.name} className="rounded-lg border border-white/10 bg-white/[0.04] p-5">
                <div className="text-sm font-semibold text-zinc-50">{plan.name}</div>
                <div className="mt-4 text-3xl font-semibold text-teal-100">{plan.price}</div>
                <p className="mt-4 text-sm leading-7 text-zinc-300">{plan.description}</p>
              </article>
            ))}
          </div>

          <div className="flex flex-wrap gap-3">
            <Link href={customerSignInUrl} className={buttonVariants({ size: "lg", className: "bg-teal-300 text-zinc-950 hover:bg-teal-200" })}>
              Open command center
            </Link>
            <Link
              href="/"
              className={buttonVariants({
                variant: "outline",
                size: "lg",
                className: "border-white/15 bg-white/[0.03] text-zinc-100 hover:bg-white/[0.08]",
              })}
            >
              Back to live system
            </Link>
          </div>
        </section>
      </div>
    </main>
  );
}
