"use client";

import { queryKeys } from "@ta/query/keys";
import type { Bot } from "@ta/types";
import { useQuery } from "@tanstack/react-query";

import { demoBots } from "../../demo/demo-bots";
import { isDemoMode, withDemoFallback } from "../../demo";
import { supabase } from "../../supabase/client";

import { useCurrentUser } from "./use-current-user";

export function useBots() {
  const { data: user } = useCurrentUser();
  return useQuery<Bot[]>({
    queryKey: queryKeys.bots.list(user?.id),
    enabled:  !!user,
    staleTime: 0,
    refetchInterval: 10_000,   // warmup_status / candles_collected change every ~10 s
    queryFn: async () => {
      if (isDemoMode) return demoBots;
      const { data, error } = await supabase
        .from("bots")
        .select("*")
        .eq("user_id", user!.id)
        .eq("is_archived", false)
        .order("created_at", { ascending: false });
      if (error) throw error;
      return withDemoFallback((data ?? []) as Bot[], demoBots);
    },
  });
}

export function useBot(botId: string | undefined) {
  const { data: user } = useCurrentUser();
  return useQuery<Bot | null>({
    queryKey: botId ? queryKeys.bots.detail(botId) : ["bots", "detail", "none"],
    enabled:  !!botId && !!user,
    staleTime: 0,
    refetchInterval: 10_000,
    queryFn: async () => {
      if (!botId) return null;
      // Only serve demo when explicitly in demo mode. Real-mode requests for
      // a missing id resolve to null so the page shows a real "not found".
      if (isDemoMode) {
        return demoBots.find((b) => b.id === botId) ?? demoBots[0] ?? null;
      }
      const { data, error } = await supabase
        .from("bots")
        .select("*")
        .eq("user_id", user!.id)
        .eq("id", botId)
        .maybeSingle();
      if (error) throw error;
      return (data ?? null) as Bot | null;
    },
  });
}
