"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools }  from "@tanstack/react-query-devtools";
import { useState, type ReactNode } from "react";

import { createQueryClient } from "./client";

interface QueryProviderProps {
  children: ReactNode;
}

/**
 * Top-level React Query provider. Mount once at the app shell root.
 *
 * Devtools render only in development.
 */
export function QueryProvider({ children }: QueryProviderProps) {
  // useState ensures the client is created once per app instance, not on every render.
  const [client] = useState(() => createQueryClient());

  return (
    <QueryClientProvider client={client}>
      {children}
      {process.env.NODE_ENV === "development" && (
        <ReactQueryDevtools initialIsOpen={false} buttonPosition="bottom-right" />
      )}
    </QueryClientProvider>
  );
}
