import type { ReactNode } from "react";

import { cn } from "@ta/utils";

import { Skeleton } from "../primitives/skeleton";

interface KpiCardProps {
  label:      string;
  value:      ReactNode;
  hint?:      ReactNode;
  trend?:     "up" | "down" | "flat";
  loading?:   boolean;
  icon?:      ReactNode;
  accent?:    "blue" | "green" | "red" | "amber" | "none";
  className?: string;
}

const ACCENT_STYLES = {
  blue:  "from-primary/10 via-transparent",
  green: "from-success/10 via-transparent",
  red:   "from-destructive/10 via-transparent",
  amber: "from-warning/10 via-transparent",
  none:  "from-transparent via-transparent",
} as const;

const ACCENT_BAR = {
  blue:  "bg-primary",
  green: "bg-success",
  red:   "bg-destructive",
  amber: "bg-warning",
  none:  "bg-transparent",
} as const;

/**
 * Premium KPI card with glassmorphism treatment and accent color bar.
 * Dark-optimised: subtle gradient background + top accent stripe.
 */
export function KpiCard({
  label, value, hint, trend, loading, icon, accent = "none", className,
}: KpiCardProps) {
  const accentKey = accent !== "none" ? accent
    : trend === "up"   ? "green"
    : trend === "down" ? "red"
    : "none";

  return (
    <div
      className={cn(
        "surface-panel relative overflow-hidden rounded-lg",
        "transition-all duration-200 hover:-translate-y-0.5 hover:border-border/85",
        className,
      )}
    >
      {/* Top accent line */}
      <div
        className={cn(
          "absolute inset-x-0 top-0 h-[2px] rounded-t-lg transition-colors",
          ACCENT_BAR[accentKey as keyof typeof ACCENT_BAR],
        )}
      />

      {/* Radial gradient wash */}
      <div
        className={cn(
          "pointer-events-none absolute inset-0 bg-gradient-to-br opacity-60",
          ACCENT_STYLES[accentKey as keyof typeof ACCENT_STYLES],
        )}
      />

      <div className="relative px-4 pb-4 pt-5">
        {/* Label row */}
        <div className="mb-2 flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            {label}
          </span>
          {icon ? (
            <span className="text-muted-foreground/50">{icon}</span>
          ) : null}
        </div>

        {/* Value */}
        {loading ? (
          <Skeleton className="h-8 w-28 rounded-md" />
        ) : (
          <div
            className={cn(
              "metric-number text-2xl font-semibold tracking-[0]",
              trend === "up"   && "text-success",
              trend === "down" && "text-destructive",
              !trend            && "text-foreground",
            )}
          >
            {value}
          </div>
        )}

        {/* Hint */}
        {hint ? (
          <div className="mt-1.5 text-[12px] text-muted-foreground">{hint}</div>
        ) : null}
      </div>
    </div>
  );
}
