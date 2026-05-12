import { isDemoMode } from "@ta/config/env";
import { createServerClient } from "@ta/supabase/server";
import { AppShell } from "@ta/ui";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { DEMO_USER } from "@/lib/demo";

import { DemoBanner }       from "@/components/layout/demo-banner";
import { KillSwitchBanner } from "@/components/layout/kill-switch-banner";
import { RealtimeBridge }   from "@/components/layout/realtime-bridge";
import { Sidebar }          from "@/components/layout/sidebar";
import { Topbar }           from "@/components/layout/topbar";

/**
 * Authenticated app shell.
 *
 * In demo mode the auth check is skipped and a synthetic user email is used
 * so the dashboard is reachable without a Supabase project.
 *
 * Otherwise: middleware enforces auth, this RSC re-validates (defense-in-
 * depth), and the topbar receives the real user email.
 */
export default async function AppShellLayout({ children }: { children: ReactNode }) {
  let email: string | null = null;

  if (isDemoMode) {
    email = DEMO_USER.email;
  } else {
    const supabase = createServerClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) {
      redirect("/sign-in");
    }
    email = user.email ?? null;
  }

  return (
    <>
      <RealtimeBridge />
      <AppShell
        sidebar={<Sidebar />}
        topBar={<Topbar email={email} />}
        banner={
          <>
            <DemoBanner />
            <KillSwitchBanner />
          </>
        }
      >
        {children}
      </AppShell>
    </>
  );
}
