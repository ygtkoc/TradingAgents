"use client";

import { queryKeys } from "@ta/query/keys";
import { edgeFn } from "@ta/supabase/edge-functions";
import type { EdgeFunctionResult } from "@ta/types";
import { useMutation, useQueryClient } from "@tanstack/react-query";

async function unwrap<T>(p: Promise<EdgeFunctionResult<T> | T>): Promise<T> {
  const res = await p;
  if (
    typeof res === "object" &&
    res !== null &&
    "ok" in res &&
    typeof (res as { ok?: unknown }).ok === "boolean"
  ) {
    const envelope = res as EdgeFunctionResult<T>;
    if (envelope.ok) return envelope.data;
    throw new Error(envelope.error.message || "Edge Function call failed");
  }
  return res as T;
}

export function useDecisionMutations() {
  const qc = useQueryClient();
  const onSuccess = () => {
    void qc.invalidateQueries({ queryKey: queryKeys.decisions.all() });
    void qc.invalidateQueries({ queryKey: queryKeys.trades.all() });
  };

  const approve = useMutation({
    mutationFn: (decisionId: string) =>
      unwrap(edgeFn.decisions.approve({ decision_id: decisionId })),
    onSuccess,
  });

  const reject = useMutation({
    mutationFn: ({ decisionId, reason }: { decisionId: string; reason: string }) =>
      unwrap(edgeFn.decisions.reject({ decision_id: decisionId, reason })),
    onSuccess,
  });

  return { approve, reject };
}
