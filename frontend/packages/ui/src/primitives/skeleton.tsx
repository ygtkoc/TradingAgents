import type { HTMLAttributes } from "react";

import { cn } from "@ta/utils";

export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-xl",
        "bg-gradient-to-r from-muted/60 via-muted-foreground/[0.04] to-muted/60",
        "bg-[length:200%_100%]",
        "animate-shimmer",
        className,
      )}
      {...props}
    />
  );
}
