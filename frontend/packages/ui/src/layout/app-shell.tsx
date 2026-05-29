import type { ReactNode } from "react";

import { cn } from "@ta/utils";

interface AppShellProps {
  sidebar?: ReactNode;
  topBar?: ReactNode;
  banner?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function AppShell({ sidebar, topBar, banner, children, className }: AppShellProps) {
  return (
    <div className={cn("system-backdrop relative flex min-h-screen w-full overflow-hidden bg-background", className)}>
      <div className="system-grid pointer-events-none fixed inset-0 opacity-45" />
      <div className="pointer-events-none fixed inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/50 to-transparent" />

      {sidebar ? (
        <aside className="relative z-10 hidden md:flex md:w-[256px] md:shrink-0 md:flex-col">
          <div className="sticky top-0 flex h-screen flex-col border-r border-border/60 bg-background/72 shadow-[24px_0_80px_rgba(0,0,0,0.22)] backdrop-blur-2xl">
            {sidebar}
          </div>
        </aside>
      ) : null}

      <div className="relative z-10 flex min-w-0 flex-1 flex-col">
        {banner ? <div className="w-full">{banner}</div> : null}

        {topBar ? (
          <header className="sticky top-0 z-20 flex shrink-0 flex-col border-b border-border/55 bg-background/76 px-4 backdrop-blur-2xl md:px-6">
            {topBar}
          </header>
        ) : null}

        <main className="relative z-0 flex-1 overflow-y-auto px-4 py-5 sm:px-6 lg:px-8 lg:py-8">
          {children}
        </main>
      </div>
    </div>
  );
}
