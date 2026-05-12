import type { ReactNode } from "react";

import { cn } from "@ta/utils";

interface PageHeaderProps {
  title:        string;
  description?: string;
  actions?:     ReactNode;
  className?:   string;
}

export function PageHeader({ title, description, actions, className }: PageHeaderProps) {
  return (
    <header
      className={cn(
        "flex flex-col gap-4 pb-2 md:flex-row md:items-start md:justify-between",
        className,
      )}
    >
      <div className="space-y-1">
        <h1 className="text-[22px] font-bold tracking-tight text-foreground">
          {title}
        </h1>
        {description ? (
          <p className="text-[13px] leading-relaxed text-muted-foreground">
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
