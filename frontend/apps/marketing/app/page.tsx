import Link from "next/link";

import { buttonVariants, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@ta/ui";

export default function HomePage() {
  const customerUrl = process.env.NEXT_PUBLIC_CUSTOMER_URL ?? "http://localhost:3001";

  return (
    <main className="system-backdrop relative min-h-screen overflow-hidden px-6 py-8 text-foreground">
      <div className="system-grid pointer-events-none absolute inset-0 opacity-45" />
      <div className="relative z-10 mx-auto flex min-h-[calc(100vh-4rem)] max-w-6xl flex-col">
        <nav className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-primary/35 bg-primary/12 text-sm font-semibold text-primary">
              L
            </div>
            <div>
              <div className="font-semibold tracking-[0]">lucrandos</div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">AI trading OS</div>
            </div>
          </div>
          <Link href={customerUrl} className={buttonVariants({ variant: "outline" })}>
            Sign in
          </Link>
        </nav>

        <section className="grid flex-1 items-center gap-8 py-16 lg:grid-cols-[1.05fr_0.95fr]">
          <div className="space-y-7">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-primary/80">
              Multi-agent trading infrastructure
            </div>
            <h1 className="max-w-3xl text-[46px] font-semibold leading-[1.02] tracking-[0] sm:text-[64px]">
              Autonomous market decisions, governed by risk.
            </h1>
            <p className="max-w-xl text-[15px] leading-7 text-muted-foreground">
              Paper trade, shadow test, and live-gate execution with agent debate, signal scoring, position lifecycle management, and auditable safety controls.
            </p>
            <div className="flex flex-wrap gap-3">
              <Link href={customerUrl} className={buttonVariants({ size: "lg" })}>
                Open command center
              </Link>
              <Link href="/pricing" className={buttonVariants({ variant: "outline", size: "lg" })}>
                Pricing
              </Link>
            </div>
          </div>

          <div className="surface-panel rounded-lg p-4">
            <div className="grid gap-3">
              {[
                { mark: "AQ", title: "Agent quorum", copy: "Technical, sentiment, risk, critique, and security agents review every signal." },
                { mark: "EP", title: "Execution pipeline", copy: "Signals become decisions, decisions pass gates, gates become paper or live positions." },
                { mark: "SC", title: "Safety control plane", copy: "Live trading is off by default and remains governed by permissions and kill switches." },
              ].map(({ mark, title, copy }) => (
                <Card key={title}>
                  <CardHeader className="flex flex-row items-center gap-3 space-y-0">
                    <div className="flex h-9 w-9 items-center justify-center rounded-md border border-border/60 bg-card/70 text-[11px] font-semibold text-primary">
                      {mark}
                    </div>
                    <div>
                      <CardTitle>{title}</CardTitle>
                      <CardDescription>{copy}</CardDescription>
                    </div>
                  </CardHeader>
                </Card>
              ))}
              <Card>
                <CardContent className="grid grid-cols-3 gap-3 pt-5">
                  {[
                    ["Modes", "3"],
                    ["Engines", "3"],
                    ["Default", "Safe"],
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-lg border border-border/45 bg-background/35 p-3">
                      <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{label}</div>
                      <div className="metric-number mt-1 text-2xl font-semibold">{value}</div>
                    </div>
                  ))}
                </CardContent>
              </Card>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
