import { Activity, BarChart3, Bot, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="system-backdrop relative grid min-h-screen grid-cols-1 overflow-hidden lg:grid-cols-[1.05fr_0.95fr]">
      <div className="system-grid pointer-events-none absolute inset-0 opacity-45" />

      <aside className="relative hidden border-r border-border/60 bg-background/55 p-12 backdrop-blur-2xl lg:flex lg:flex-col lg:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-lg border border-primary/35 bg-primary/12">
            <Activity className="h-5 w-5 text-primary" />
          </div>
          <div>
            <div className="text-[16px] font-semibold tracking-[0] text-foreground">lucrandos</div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              AI trading OS
            </div>
          </div>
        </div>

        <div className="max-w-xl space-y-6">
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-primary/80">
            Autonomous decision infrastructure
          </div>
          <h2 className="text-[42px] font-semibold leading-[1.05] tracking-[0] text-foreground">
            Multi-agent trading with institutional safety rails.
          </h2>
          <p className="max-w-md text-[14px] leading-7 text-muted-foreground">
            Agents analyze markets, critique decisions, enforce risk, and route execution through audited gates before a trade can move.
          </p>
          <div className="grid gap-3">
            {[
              { icon: Bot, label: "Agent quorum", copy: "analysis, sentiment, risk, critique, security" },
              { icon: BarChart3, label: "Market intelligence", copy: "live price feeds and technical state" },
              { icon: ShieldCheck, label: "Fail-closed execution", copy: "kill switch, approval, and permission gates" },
            ].map(({ icon: Icon, label, copy }) => (
              <div key={label} className="surface-panel flex items-center gap-3 rounded-lg p-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-md border border-border/60 bg-card/70">
                  <Icon className="h-4 w-4 text-primary" />
                </div>
                <div>
                  <div className="text-[13px] font-semibold text-foreground">{label}</div>
                  <div className="text-[12px] text-muted-foreground">{copy}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3">
          {[
            { label: "Modes", value: "3", hint: "paper / shadow / live" },
            { label: "Engines", value: "3", hint: "agent / execution / position" },
            { label: "Posture", value: "safe", hint: "live off by default" },
          ].map((item) => (
            <div key={item.label} className="rounded-lg border border-border/55 bg-card/45 p-3">
              <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{item.label}</div>
              <div className="metric-number mt-1 text-[20px] font-semibold text-foreground">{item.value}</div>
              <div className="text-[10px] text-muted-foreground/70">{item.hint}</div>
            </div>
          ))}
        </div>
      </aside>

      <main className="relative z-10 flex items-center justify-center p-6 sm:p-12">
        <div className="w-full max-w-sm">{children}</div>
      </main>
    </div>
  );
}
