import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { createServerClient } from "@ta/supabase/server";
import { AppShell, Badge } from "@ta/ui";
import { cn } from "@ta/utils";

const navSections = [
  {
    title: "Command",
    items: [
      ["OV", "Overview", "/overview"],
      ["US", "Users", "/users"],
      ["BR", "Trading brain", "/trading-brain"],
    ],
  },
  {
    title: "Trading",
    items: [
      ["TR", "Trades", "/trades"],
      ["DC", "Decisions", "/decisions"],
      ["AR", "Agent runs", "/agent-runs"],
      ["RC", "Reconciliation", "/reconciliation"],
    ],
  },
  {
    title: "Logs",
    items: [
      ["SC", "Security logs", "/logs/security"],
      ["RK", "Risk logs", "/logs/risk"],
      ["AU", "Audit logs", "/logs/audit"],
    ],
  },
  {
    title: "System",
    items: [
      ["PS", "Platform settings", "/system/platform-settings"],
      ["KS", "Kill switch", "/operations/kill-switch"],
    ],
  },
];

export default async function AdminShellLayout({ children }: { children: ReactNode }) {
  const supabase = createServerClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const role = (user?.app_metadata?.role as string | undefined) ?? "user";
  const profileResult = user
    ? await supabase.from("profiles").select("role").eq("id", user.id).maybeSingle()
    : { data: null };
  const profile = profileResult.data as { role?: string } | null;
  const profileRole = (profile?.role as string | undefined) ?? role;
  const isAdminRole = ["admin", "super_admin", "security_admin"].includes(profileRole);

  if (!user || !isAdminRole) {
    notFound();
  }

  return (
    <AppShell
      banner={
        <div className="border-b border-sky-500/15 bg-sky-500/8 px-4 py-2 text-center text-xs font-medium text-sky-300">
          Lucrandos admin plane. Every privileged action should remain auditable.
        </div>
      }
      sidebar={
        <nav className="flex h-full flex-col bg-[#080b10] p-4 text-sm">
          <div className="mb-5 rounded-xl border border-white/10 bg-white/[0.045] p-4 shadow-[0_16px_60px_rgba(0,0,0,0.28)]">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-cyan-400 text-sm font-black text-slate-950">L</div>
              <div>
                <div className="text-[15px] font-semibold tracking-[0] text-foreground">Lucrandos</div>
                <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">Admin OS</div>
              </div>
            </div>
          </div>
          <div className="min-h-0 flex-1 space-y-5 overflow-y-auto pr-1">
            {navSections.map((section) => (
              <div key={section.title}>
                <div className="mb-2 px-2 text-[10px] font-black uppercase tracking-[0.18em] text-muted-foreground/65">
                  {section.title}
                </div>
                <div className="space-y-1">
                  {section.items.map(([code, label, href]) => (
                    <a
                      key={href}
                      className={cn(
                        "group flex items-center gap-3 rounded-lg px-2.5 py-2.5 text-muted-foreground transition-all",
                        "hover:bg-white/[0.065] hover:text-foreground",
                      )}
                      href={href}
                    >
                      <span className="flex h-7 w-7 items-center justify-center rounded-md border border-white/10 bg-white/[0.04] text-[10px] font-black text-cyan-200 group-hover:border-cyan-300/35 group-hover:bg-cyan-300/10">
                        {code}
                      </span>
                      <span className="truncate text-[13px] font-semibold">{label}</span>
                    </a>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </nav>
      }
      topBar={
        <div className="flex h-16 w-full items-center justify-between">
          <div>
            <div className="text-sm font-semibold tracking-[0] text-foreground">Operations cockpit</div>
            <div className="text-[11px] text-muted-foreground">Monitoring, controls, and platform intelligence</div>
          </div>
          <div className="flex items-center gap-3">
            <Badge variant="warning">{profileRole}</Badge>
            <span className="hidden text-xs text-muted-foreground sm:block">{user.email}</span>
          </div>
        </div>
      }
    >
      {children}
    </AppShell>
  );
}
