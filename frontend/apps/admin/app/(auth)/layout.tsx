import type { ReactNode } from "react";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="system-backdrop relative flex min-h-screen items-center justify-center overflow-hidden px-4">
      <div className="system-grid pointer-events-none absolute inset-0 opacity-45" />
      <div className="relative z-10">{children}</div>
    </div>
  );
}
