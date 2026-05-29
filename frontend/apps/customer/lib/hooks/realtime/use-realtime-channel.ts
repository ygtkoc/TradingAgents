"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { isDemoMode } from "../../demo";
import { supabase } from "../../supabase/client";

interface UseRealtimeChannelOptions {
  /** Stable channel name; one channel per logical concern. */
  channel: string;
  table:   string;
  event?:  "INSERT" | "UPDATE" | "DELETE" | "*";
  schema?: string;
  filter?: string;             // e.g. `user_id=eq.<uuid>`
  /** Query keys to invalidate when an event fires. */
  invalidateKeys: readonly (readonly unknown[])[];
  enabled?: boolean;
}

/**
 * Subscribe to Supabase Realtime for a single concern. On any matching change,
 * the listed React Query keys are invalidated so the next consumer pulls fresh
 * data from the server. UI updates flow through React Query, not via direct
 * cache writes — server remains the source of truth.
 *
 * Disabled entirely in demo mode (no Supabase backend assumed).
 */
export function useRealtimeChannel({
  channel,
  table,
  event = "*",
  schema = "public",
  filter,
  invalidateKeys,
  enabled = true,
}: UseRealtimeChannelOptions) {
  const qc = useQueryClient();

  useEffect(() => {
    if (!enabled || isDemoMode) return;

    const ch = supabase
      .channel(channel)
      .on(
        "postgres_changes",
        { event, schema, table, filter },
        () => {
          for (const key of invalidateKeys) {
            void qc.invalidateQueries({ queryKey: key as unknown[] });
          }
        },
      )
      .subscribe();

    return () => {
      void supabase.removeChannel(ch);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channel, table, event, schema, filter, enabled]);
}
