"use client";

import { queryKeys } from "@ta/query/keys";
import type { Notification } from "@ta/types";
import { useQuery } from "@tanstack/react-query";

import { demoNotifications } from "../../demo/demo-notifications";
import { isDemoMode, withDemoFallback } from "../../demo";
import { supabase } from "../../supabase/client";

import { useCurrentUser } from "./use-current-user";

export function useNotifications(limit = 50) {
  const { data: user } = useCurrentUser();
  return useQuery<Notification[]>({
    queryKey: queryKeys.notifications.list(user?.id),
    enabled:  !!user,
    staleTime: 0,
    queryFn: async () => {
      if (isDemoMode) return demoNotifications.slice(0, limit);
      const { data, error } = await supabase
        .from("notifications")
        .select("*")
        .order("created_at", { ascending: false })
        .limit(limit);
      if (error) throw error;
      return withDemoFallback(
        (data ?? []) as Notification[],
        demoNotifications.slice(0, limit),
      );
    },
  });
}

export function useUnreadNotificationCount() {
  const { data: user } = useCurrentUser();
  return useQuery<number>({
    queryKey: queryKeys.notifications.unread(user?.id),
    enabled:  !!user,
    staleTime: 0,
    queryFn: async () => {
      if (isDemoMode) return demoNotifications.filter((n) => !n.read).length;
      const { count, error } = await supabase
        .from("notifications")
        .select("id", { count: "exact", head: true })
        .eq("read", false);
      if (error) throw error;
      return count ?? 0;
    },
  });
}
