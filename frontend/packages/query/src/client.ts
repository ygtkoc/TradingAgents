import { QueryClient } from "@tanstack/react-query";

/**
 * Default QueryClient factory.
 *
 * Defaults reflect the architecture:
 *   - 30s staleTime for "warm" data (lists, kpis).
 *   - retry once on read; never retry on mutation (idempotency keys handle it).
 *   - GC after 5 min.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime:    5 * 60_000,
        retry:     1,
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: 0,
      },
    },
  });
}
