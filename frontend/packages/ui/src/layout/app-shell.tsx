import type { ReactNode } from "react";

import { cn } from "@ta/utils";

interface AppShellProps {
  sidebar?:   ReactNode;
  topBar?:    ReactNode;
  banner?:    ReactNode;
  children:   ReactNode;
  className?: string;
}

/**
 * Premium dark-fintech app shell.
 * Sidebar: fixed-width glassy panel with subtle right border.
 * Topbar:  sticky, blurred, translucent — floats over content.
 * Main:    scrollable with generous padding.
 */
export function AppShell({ sidebar, topBar, banner, children, className }: AppShellProps) {
  return (
    <div className={cn("flex min-h-screen w-full bg-background", className)}>
      {/* ── Sidebar (desktop) ────────────────────────────────────────────────── */}
      {sidebar ? (
        <aside className="hidden md:flex md:w-[220px] md:shrink-0 md:flex-col">
          {/* Sticky inner so it doesn't scroll with content */}
          <div className="sticky top-0 flex h-screen flex-col border-r border-border/50 bg-card/60 backdrop-blur-xl">
            {sidebar}
          </div>
        </aside>
      ) : null}

      {/* ── Main column ──────────────────────────────────────────────────────── */}
      <div className="flex flex-1 flex-col min-w-0">
        {/* Banners (kill-switch, demo) */}
        {banner ? <div className="w-full">{banner}</div> : null}

        {/* Topbar */}
        {topBar ? (
          <header className="sticky top-0 z-20 flex shrink-0 flex-col border-b border-border/40 bg-background/70 px-5 backdrop-blur-xl">
            {topBar}
          </header>
        ) : null}

        {/* Page content */}
        <main className="relative z-0 flex-1 overflow-y-auto p-6 lg:p-8">
          {children}
        </main>
      </div>
    </div>
  );
}
