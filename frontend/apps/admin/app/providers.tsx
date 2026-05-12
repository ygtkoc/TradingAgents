"use client";

import type { ReactNode } from "react";

import { QueryProvider } from "@ta/query/provider";

export function Providers({ children }: { children: ReactNode }) {
  return <QueryProvider>{children}</QueryProvider>;
}
