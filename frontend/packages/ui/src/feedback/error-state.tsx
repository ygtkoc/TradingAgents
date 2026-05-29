"use client";

import { AlertTriangle } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@ta/utils";

import { Button } from "../primitives/button";

interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
  details?: ReactNode;
  className?: string;
}

export function ErrorState({
  title   = "Something went wrong",
  message = "We could not load this section. Please try again.",
  onRetry,
  details,
  className,
}: ErrorStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center gap-3 rounded-lg border border-destructive/30 bg-destructive/10 p-6 text-center backdrop-blur-sm",
        className,
      )}
    >
      <AlertTriangle className="h-6 w-6 text-destructive" />
      <h3 className="text-[13px] font-semibold text-foreground">{title}</h3>
      <p className="max-w-md text-[12px] text-muted-foreground">{message}</p>
      {onRetry ? (
        <Button size="sm" variant="outline" onClick={onRetry} className="mt-2">
          Try again
        </Button>
      ) : null}
      {details ? (
        <details className="mt-3 w-full text-left text-xs text-muted-foreground">
          <summary className="cursor-pointer">Technical details</summary>
          <pre className="mt-2 max-h-40 overflow-auto rounded bg-muted/40 p-2">
            {details}
          </pre>
        </details>
      ) : null}
    </div>
  );
}
