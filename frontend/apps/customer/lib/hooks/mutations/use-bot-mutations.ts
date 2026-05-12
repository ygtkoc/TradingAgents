"use client";

import { queryKeys } from "@ta/query/keys";
import { edgeFn } from "@ta/supabase/edge-functions";
import { useMutation, useQueryClient } from "@tanstack/react-query";

/**
 * Bot lifecycle actions — all routed through Edge Functions.
 * NO direct DB writes allowed for bots.status.
 */
export function useBotMutations() {
  const qc = useQueryClient();
  const onSuccess = () => {
    void qc.invalidateQueries({ queryKey: queryKeys.bots.all() });
  };

  const start = useMutation({
    mutationFn: (botId: string) => edgeFn.bots.activate({ bot_id: botId }),
    onSuccess,
  });
  const pause = useMutation({
    mutationFn: (botId: string) => edgeFn.bots.pause({ bot_id: botId }),
    onSuccess,
  });
  const archive = useMutation({
    mutationFn: (botId: string) => edgeFn.bots.archive({ bot_id: botId }),
    onSuccess,
  });

  return { start, pause, archive };
}
