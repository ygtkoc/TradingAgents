import type { ReactNode } from "react";

import { cn } from "@ta/utils";

interface ProductPageProps {
  children: ReactNode;
  size?: "md" | "lg" | "xl";
  className?: string;
}

const SIZE = {
  md: "max-w-4xl",
  lg: "max-w-6xl",
  xl: "max-w-7xl",
} as const;

export function ProductPage({ children, size = "xl", className }: ProductPageProps) {
  return (
    <div className={cn("mx-auto flex w-full flex-col gap-5", SIZE[size], className)}>
      {children}
    </div>
  );
}

interface IntelligenceCardProps {
  title: string;
  value: ReactNode;
  label?: string;
  tone?: "blue" | "cyan" | "emerald" | "amber" | "purple" | "risk" | "neutral";
  children?: ReactNode;
  className?: string;
}

const TONE = {
  blue: "from-primary/16 text-primary",
  cyan: "from-cyan-300/16 text-cyan-300",
  emerald: "from-success/16 text-success",
  amber: "from-warning/16 text-warning",
  purple: "from-violet-300/16 text-violet-300",
  risk: "from-destructive/16 text-destructive",
  neutral: "from-white/6 text-foreground",
} as const;

export function IntelligenceCard({
  title,
  value,
  label,
  tone = "neutral",
  children,
  className,
}: IntelligenceCardProps) {
  return (
    <div className={cn("surface-panel relative overflow-hidden rounded-lg p-4", className)}>
      <div className={cn("pointer-events-none absolute inset-0 bg-gradient-to-br to-transparent opacity-80", TONE[tone])} />
      <div className="relative">
        <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
          {title}
        </div>
        <div className="metric-number mt-2 text-2xl font-semibold tracking-[0] text-foreground">
          {value}
        </div>
        {label ? <div className="mt-1 text-[12px] text-muted-foreground">{label}</div> : null}
        {children ? <div className="mt-4">{children}</div> : null}
      </div>
    </div>
  );
}

interface PipelineStepProps {
  label: string;
  state?: "complete" | "active" | "idle" | "risk";
}

export function PipelineRail({ steps }: { steps: PipelineStepProps[] }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
      {steps.map((step, index) => (
        <div
          key={`${step.label}-${index}`}
          className={cn(
            "relative rounded-lg border bg-card/45 px-3 py-3 text-[12px]",
            step.state === "active" && "border-primary/45 bg-primary/10 text-primary",
            step.state === "complete" && "border-success/35 bg-success/10 text-success",
            step.state === "risk" && "border-destructive/35 bg-destructive/10 text-destructive",
            (!step.state || step.state === "idle") && "border-border/55 text-muted-foreground",
          )}
        >
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "h-2 w-2 rounded-full",
                step.state === "active" && "bg-primary shadow-[0_0_16px_hsl(var(--primary)/0.55)]",
                step.state === "complete" && "bg-success",
                step.state === "risk" && "bg-destructive",
                (!step.state || step.state === "idle") && "bg-muted-foreground/35",
              )}
            />
            <span className="font-semibold">{step.label}</span>
          </div>
        </div>
      ))}
    </div>
  );
}
