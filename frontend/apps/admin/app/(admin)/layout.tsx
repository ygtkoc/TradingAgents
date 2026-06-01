import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { createServerClient } from "@ta/supabase/server";
import { AppShell, Badge } from "@ta/ui";

import { AdminSidebar } from "./_components/admin-sidebar";

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
        <div className="border-b border-slate-800 bg-[#0f1720] px-4 py-2 text-center text-xs font-medium text-slate-300">
          Lucrandos admin console. Privileged changes are auditable.
        </div>
      }
      sidebar={<AdminSidebar />}
      topBar={
        <div className="flex min-h-16 w-full items-center justify-between gap-3 py-3">
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-white">Operations cockpit</div>
            <div className="truncate text-[12px] text-slate-400">Monitoring, controls, and platform intelligence</div>
          </div>
          <div className="flex min-w-0 items-center gap-2">
            <Badge variant="secondary" className="border-slate-700 bg-slate-800 text-slate-100">{profileRole}</Badge>
            <span className="hidden max-w-[220px] truncate text-xs text-slate-400 sm:block">{user.email}</span>
          </div>
        </div>
      }
    >
      {children}
    </AppShell>
  );
}
