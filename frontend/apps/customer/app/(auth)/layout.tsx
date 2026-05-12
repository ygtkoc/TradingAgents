import { Activity, BarChart3, Bot, Shield } from "lucide-react";
import type { ReactNode } from "react";

/**
 * Premium dark split-card auth layout.
 * Left: brand panel with fintech gradients, stats, features.
 * Right: the auth form, centered on a deep dark bg.
 */
export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-h-screen grid-cols-1 lg:grid-cols-2">
      {/* ── Left: Brand panel ─────────────────────────────────────────────── */}
      <aside className="relative hidden overflow-hidden bg-card/40 lg:flex lg:flex-col lg:justify-between lg:p-12">
        {/* Background gradients */}
        <div className="pointer-events-none absolute inset-0">
          <div className="absolute -left-24 -top-24 h-96 w-96 rounded-full bg-primary/8 blur-3xl" />
          <div className="absolute -bottom-24 -right-24 h-64 w-64 rounded-full bg-success/6 blur-3xl" />
          {/* Subtle grid */}
          <div className="absolute inset-0 bg-[linear-gradient(hsl(var(--border)/0.15)_1px,transparent_1px),linear-gradient(90deg,hsl(var(--border)/0.15)_1px,transparent_1px)] bg-[size:32px_32px]" />
          {/* Right edge fade */}
          <div className="absolute inset-y-0 right-0 w-24 bg-gradient-to-l from-background to-transparent" />
        </div>

        {/* Brand mark */}
        <div className="relative flex items-center gap-2.5">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/15 ring-1 ring-primary/20">
            <Activity className="h-5 w-5 text-primary" />
          </div>
          <div>
            <div className="text-[15px] font-bold tracking-tight text-foreground">TradingAgents</div>
            <div className="text-[10px] text-muted-foreground/60">Multi-agent AI trading</div>
          </div>
        </div>

        {/* Hero copy */}
        <div className="relative space-y-4">
          <h2 className="text-[28px] font-bold leading-snug tracking-tight text-foreground">
            Multi-agent AI trading,<br />with the safety rails on.
          </h2>
          <p className="max-w-sm text-[13px] leading-relaxed text-muted-foreground">
            Paper trade, shadow test, and execute live — with reconciliation,
            kill switches, and full audit logging built in from day one.
          </p>

          {/* Feature list */}
          <div className="mt-2 space-y-2.5">
            {[
              { icon: Bot,      label: "5+ AI agents vote on every trade signal" },
              { icon: BarChart3, label: "15+ technical indicators analyzed in real-time" },
              { icon: Shield,   label: "Risk, security & sentiment filters on every decision" },
            ].map(({ icon: Icon, label }) => (
              <div key={label} className="flex items-center gap-2.5 text-[12px] text-muted-foreground">
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                  <Icon className="h-3.5 w-3.5 text-primary" />
                </div>
                {label}
              </div>
            ))}
          </div>
        </div>

        {/* Bottom stats */}
        <div className="relative grid grid-cols-3 gap-3">
          {[
            { label: "Modes",   value: "3",           hint: "paper · shadow · live" },
            { label: "Engines", value: "3",           hint: "agent · execution · position" },
            { label: "Default", value: "fail-closed", hint: "safety first" },
          ].map(({ label, value, hint }) => (
            <div
              key={label}
              className="rounded-xl border border-border/40 bg-card/40 p-3 backdrop-blur-sm"
            >
              <div className="text-[9px] font-semibold uppercase tracking-[0.12em] text-muted-foreground/50">{label}</div>
              <div className="mt-1 text-[15px] font-bold text-foreground">{value}</div>
              <div className="mt-0.5 text-[10px] text-muted-foreground/60">{hint}</div>
            </div>
          ))}
        </div>
      </aside>

      {/* ── Right: Form area ────────────────────────────────────────────────── */}
      <main className="flex items-center justify-center bg-background p-6 sm:p-12">
        <div className="w-full max-w-sm">{children}</div>
      </main>
    </div>
  );
}
