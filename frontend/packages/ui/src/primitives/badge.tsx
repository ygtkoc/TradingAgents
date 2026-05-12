import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";

import { cn } from "@ta/utils";

const badgeVariants = cva(
  [
    "inline-flex items-center gap-1 rounded-full px-2 py-0.5",
    "text-[11px] font-semibold leading-none tracking-wide",
    "border transition-colors",
  ].join(" "),
  {
    variants: {
      variant: {
        default:     "border-primary/30    bg-primary/15    text-primary",
        secondary:   "border-border/60     bg-secondary/60  text-muted-foreground",
        destructive: "border-destructive/30 bg-destructive/12 text-destructive",
        success:     "border-success/30    bg-success/12    text-success",
        warning:     "border-warning/30    bg-warning/12    text-warning",
        outline:     "border-border        bg-transparent   text-foreground",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps
  extends HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { badgeVariants };
