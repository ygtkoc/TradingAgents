// No "use client" — Button is a styled <button> wrapper with no hooks.
// `buttonVariants` is a pure cva() result that must be importable from RSCs.
import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ButtonHTMLAttributes } from "react";

import { cn } from "@ta/utils";

const buttonVariants = cva(
  [
    "inline-flex items-center justify-center whitespace-nowrap rounded-lg",
    "text-[13px] font-semibold tracking-[0.01em]",
    "ring-offset-background transition-all duration-150",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
    "disabled:pointer-events-none disabled:opacity-40",
    "active:scale-[0.97]",
  ].join(" "),
  {
    variants: {
      variant: {
        default: [
          "bg-primary text-primary-foreground",
          "shadow-[0_1px_3px_rgba(0,0,0,0.4),inset_0_1px_0_rgba(255,255,255,0.08)]",
          "hover:bg-primary/90 hover:shadow-[0_0_12px_hsl(var(--primary)/0.35)]",
        ].join(" "),
        destructive: [
          "bg-destructive/90 text-destructive-foreground",
          "hover:bg-destructive hover:shadow-[0_0_12px_hsl(var(--destructive)/0.3)]",
        ].join(" "),
        outline: [
          "border border-border/80 bg-transparent text-foreground",
          "hover:bg-white/[0.04] hover:border-border",
        ].join(" "),
        secondary: [
          "bg-secondary text-secondary-foreground",
          "hover:bg-secondary/70",
        ].join(" "),
        ghost: "text-muted-foreground hover:bg-white/[0.05] hover:text-foreground",
        link:  "text-primary underline-offset-4 hover:underline p-0 h-auto",
      },
      size: {
        default: "h-9  px-4 py-2",
        sm:      "h-8  px-3 text-[12px]",
        lg:      "h-10 px-6 text-[14px]",
        icon:    "h-9  w-9",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  ),
);
Button.displayName = "Button";

export { buttonVariants };
