"use client";

import { queryKeys } from "@ta/query/keys";
import { edgeFn } from "@ta/supabase/edge-functions";
import { useMutation, useQueryClient } from "@tanstack/react-query";

export function useDecisionMutations() {
  const qc = useQueryClient();
  const onSuccess = () => {
    void qc.invalidateQueries({ queryKey: queryKeys.decisions.all() });
    void qc.invalidateQueries({ queryKey: queryKeys.trades.all() });
  };

  const approve = useMutation({
    mutationFn: (decisionId: string) =>
      edgeFn.decisions.approve({ decision_id: decisionId }),
    onSuccess,
  });

  const reject = useMutation({
    mutationFn: ({ decisionId, reason }: { decisionId: string; reason: string }) =>
      edgeFn.decisions.reject({ decision_id: decisionId, reason }),
    onSuccess,
  });

  return { approve, reject };
}
