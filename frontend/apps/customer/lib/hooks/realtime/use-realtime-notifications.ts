"use client";

import { queryKeys } from "@ta/query/keys";

import { useCurrentUser } from "../queries/use-current-user";

import { useRealtimeChannel } from "./use-realtime-channel";

export function useRealtimeNotifications() {
  const { data: user } = useCurrentUser();
  useRealtimeChannel({
    channel: `notifications:${user?.id ?? "anon"}`,
    table:   "notifications",
    filter:  user ? `user_id=eq.${user.id}` : undefined,
    enabled: !!user,
    invalidateKeys: [
      queryKeys.notifications.list(user?.id),
      queryKeys.notifications.unread(user?.id),
    ],
  });
}
