import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { createServerClient } from "@ta/supabase/server";
import { AppShell, Badge } from "@ta/ui";

/**
 * Admin shell. Defense-in-depth: middleware already gated, but RSC re-checks
 * the JWT and the role claim. Falls through to 404 if not admin.
 */
export default async function AdminShellLayout({ children }: { children: ReactNode }) {
  const supabase = createServerClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const role = (user?.app_metadata?.role as string | undefined) ?? "user";
  if (!user || role !== "admin") {
    notFound();
  }

  return (
    <AppShell
      banner={
        <div className="bg-warning/15 px-4 py-2 text-center text-xs font-medium text-warning-foreground">
          Admin console — actions are audited.
        </div>
      }
      sidebar={
        <nav className="flex flex-col gap-1 p-4 text-sm">
          <span className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Admin
          </span>
          <a className="rounded px-2 py-1 hover:bg-accent" href="/overview">Overview</a>
          <a className="rounded px-2 py-1 hover:bg-accent" href="/users">Users</a>
          <a className="rounded px-2 py-1 hover:bg-accent" href="/trades">Trades</a>
          <a className="rounded px-2 py-1 hover:bg-accent" href="/decisions">Decisions</a>
          <a className="rounded px-2 py-1 hover:bg-accent" href="/agent-runs">Agent runs</a>
          <a className="rounded px-2 py-1 hover:bg-accent" href="/reconciliation">Reconciliation</a>
          <a className="rounded px-2 py-1 hover:bg-accent" href="/logs/security">Security logs</a>
          <a className="rounded px-2 py-1 hover:bg-accent" href="/logs/risk">Risk logs</a>
          <a className="rounded px-2 py-1 hover:bg-accent" href="/logs/audit">Audit logs</a>
          <a className="rounded px-2 py-1 hover:bg-accent" href="/system/platform-settings">Platform settings</a>
          <a className="rounded px-2 py-1 hover:bg-accent" href="/operations/kill-switch">Kill switch</a>
        </nav>
      }
      topBar={
        <div className="flex w-full items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold">lucrandos Admin</span>
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
