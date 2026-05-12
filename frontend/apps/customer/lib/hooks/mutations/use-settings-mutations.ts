"use client";

import { queryKeys } from "@ta/query/keys";
import { edgeFn } from "@ta/supabase/edge-functions";
import type { UserSettingsUpdateRequest } from "@ta/types";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useCurrentUser } from "../queries/use-current-user";

export function useUpdateUserSettings() {
  const qc = useQueryClient();
  const { data: user } = useCurrentUser();

  return useMutation({
    mutationFn: (body: UserSettingsUpdateRequest) =>
      edgeFn.userSettings.update(body),
    onSuccess: () => {
      if (user) {
        void qc.invalidateQueries({ queryKey: queryKeys.userSettings.detail(user.id) });
      }
    },
  });
}
