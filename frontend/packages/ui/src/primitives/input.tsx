import { forwardRef, type InputHTMLAttributes } from "react";

import { cn } from "@ta/utils";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      ref={ref}
      type={type}
      className={cn(
        "flex h-10 w-full rounded-md border border-border/65 bg-card/70",
        "px-3 py-2 text-[13px] text-foreground",
        "placeholder:text-muted-foreground/40",
        "transition-all duration-150",
        "focus-visible:border-ring/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
        "hover:border-border",
        "disabled:cursor-not-allowed disabled:opacity-50",
        "file:border-0 file:bg-transparent file:text-sm file:font-medium",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";
