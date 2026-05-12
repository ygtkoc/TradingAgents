"use client";

import type { ReactNode } from "react";

import { QueryProvider } from "@ta/query/provider";

/** Top-level client providers — keeps `app/layout.tsx` server-rendered. */
export function Providers({ children }: { children: ReactNode }) {
  return <QueryProvider>{children}</QueryProvider>;
}
