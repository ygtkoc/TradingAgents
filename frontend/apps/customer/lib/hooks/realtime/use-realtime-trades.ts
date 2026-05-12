"use client";

import { queryKeys } from "@ta/query/keys";

import { useCurrentUser } from "../queries/use-current-user";

import { useRealtimeChannel } from "./use-realtime-channel";

/** Live updates for the user's open trades. */
export function useRealtimeOpenTrades() {
  const { data: user } = useCurrentUser();
  useRealtimeChannel({
    channel: `trades-open:${user?.id ?? "anon"}`,
    table:   "trades",
    filter:  user ? `user_id=eq.${user.id}` : undefined,
    enabled: !!user,
    invalidateKeys: [
      queryKeys.trades.all(),
      queryKeys.trades.open(user?.id),
    ],
  });
}
