import type { ReactNode } from "react";

import { cn } from "@ta/utils";

interface PageHeaderProps {
  title: string;
  description?: string;
  eyebrow?: string;
  actions?: ReactNode;
  className?: string;
}

export function PageHeader({ title, description, eyebrow, actions, className }: PageHeaderProps) {
  return (
    <header
      className={cn(
        "surface-panel relative overflow-hidden rounded-lg px-5 py-5 sm:px-6",
        "flex flex-col gap-4 md:flex-row md:items-center md:justify-between",
        className,
      )}
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-primary/60 via-cyan-300/40 to-transparent" />
      <div className="min-w-0 space-y-2">
        {eyebrow ? (
          <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-primary/80">
            {eyebrow}
          </div>
        ) : null}
        <h1 className="text-[26px] font-semibold leading-tight tracking-[0] text-foreground sm:text-[30px]">
          {title}
        </h1>
        {description ? (
          <p className="max-w-3xl text-[13px] leading-6 text-muted-foreground">
            {description}
          </p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {actions}
        </div>
      ) : null}
    </header>
  );
}
