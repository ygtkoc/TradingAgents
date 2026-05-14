"use client";

import { useCurrentUser } from "../queries/use-current-user";

import { useRealtimeChannel } from "./use-realtime-channel";

export function useRealtimePaperAccount() {
  const { data: user } = useCurrentUser();
  useRealtimeChannel({
    channel: `paper-account:${user?.id ?? "anon"}`,
    table: "paper_accounts",
    filter: user ? `user_id=eq.${user.id}` : undefined,
    enabled: !!user,
    invalidateKeys: [
      ["paper-account", user?.id],
      ["paper-account-events", user?.id],
    ],
  });
}
