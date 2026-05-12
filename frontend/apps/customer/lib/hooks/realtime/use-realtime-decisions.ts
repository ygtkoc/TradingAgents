"use client";

import { queryKeys } from "@ta/query/keys";

import { useCurrentUser } from "../queries/use-current-user";

import { useRealtimeChannel } from "./use-realtime-channel";

/** Live updates for the user's pending-approval decisions. */
export function useRealtimePendingDecisions() {
  const { data: user } = useCurrentUser();
  useRealtimeChannel({
    channel: `decisions-pending:${user?.id ?? "anon"}`,
    table:   "trade_decisions",
    filter:  user ? `user_id=eq.${user.id}` : undefined,
    enabled: !!user,
    invalidateKeys: [
      queryKeys.decisions.all(),
      queryKeys.decisions.pendingApproval(user?.id),
    ],
  });
}
