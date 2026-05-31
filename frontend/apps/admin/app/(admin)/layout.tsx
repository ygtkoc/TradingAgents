import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { createServerClient } from "@ta/supabase/server";
import { AppShell, Badge } from "@ta/ui";

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

  const links = [
    ["Overview", "/overview"],
    ["Users", "/users"],
    ["Trades", "/trades"],
    ["Decisions", "/decisions"],
    ["Agent runs", "/agent-runs"],
    ["Trading brain", "/trading-brain"],
    ["Reconciliation", "/reconciliation"],
    ["Security logs", "/logs/security"],
    ["Risk logs", "/logs/risk"],
    ["Audit logs", "/logs/audit"],
    ["Platform settings", "/system/platform-settings"],
    ["Kill switch", "/operations/kill-switch"],
  ];

  return (
    <AppShell
      banner={
        <div className="border-b border-warning/20 bg-warning/12 px-4 py-2 text-center text-xs font-medium text-warning">
          Admin console: privileged actions are audited.
        </div>
      }
      sidebar={
        <nav className="flex h-full flex-col gap-1 p-4 text-sm">
          <div className="mb-4 rounded-lg border border-border/60 bg-card/45 p-3">
            <div className="text-[15px] font-semibold">lucrandos Admin</div>
            <div className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">Operations plane</div>
          </div>
          <span className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            Control surfaces
          </span>
          {links.map(([label, href]) => (
            <a key={href} className="rounded-md px-3 py-2 text-muted-foreground transition-colors hover:bg-white/[0.055] hover:text-foreground" href={href}>
              {label}
            </a>
          ))}
        </nav>
      }
      topBar={
        <div className="flex h-14 w-full items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold">Admin operations</span>
            <Badge variant="warning">admin</Badge>
          </div>
          <span className="text-xs text-muted-foreground">{user.email}</span>
        </div>
      }
    >
      {children}
    </AppShell>
  );
}
