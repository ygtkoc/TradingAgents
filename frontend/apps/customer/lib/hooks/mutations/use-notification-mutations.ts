"use client";

import { queryKeys } from "@ta/query/keys";
import { edgeFn } from "@ta/supabase/edge-functions";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useCurrentUser } from "../queries/use-current-user";

export function useNotificationMutations() {
  const qc = useQueryClient();
  const { data: user } = useCurrentUser();

  const onSuccess = () => {
    void qc.invalidateQueries({ queryKey: queryKeys.notifications.list(user?.id) });
    void qc.invalidateQueries({ queryKey: queryKeys.notifications.unread(user?.id) });
  };

  const markRead = useMutation({
    mutationFn: (notificationIds: string[]) =>
      edgeFn.notifications.markRead({ notification_ids: notificationIds }),
    onSuccess,
  });

  const markAllRead = useMutation({
    mutationFn: () => edgeFn.notifications.markAllRead(),
    onSuccess,
  });

  return { markRead, markAllRead };
}
