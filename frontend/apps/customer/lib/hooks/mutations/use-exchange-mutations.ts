"use client";

import { edgeFn } from "@ta/supabase/edge-functions";
import type {
  EdgeFunctionResult,
  ExchangeConnectionCreateResponse,
} from "@ta/types/edge-functions";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useCurrentUser } from "../queries/use-current-user";

export function useExchangeMutations() {
  const qc = useQueryClient();
  const { data: user } = useCurrentUser();

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["exchange-connections", user?.id] });

  const create = useMutation({
    mutationFn: async (body: { exchange: string; label: string; api_key: string; api_secret: string }) => {
      const response = await fetch("/api/exchange-connections", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const result = await response.json() as EdgeFunctionResult<ExchangeConnectionCreateResponse>;
      return result;
    },
    onSuccess: invalidate,
  });

  const test = useMutation({
    mutationFn: (connection_id: string) =>
      edgeFn.exchangeConnections.test({ connection_id }),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: (connection_id: string) =>
      edgeFn.exchangeConnections.delete({ connection_id }),
    onSuccess: invalidate,
  });

  const toggleLive = useMutation({
    mutationFn: (body: { connection_id: string; enable: boolean; risk_acknowledged: boolean }) =>
      edgeFn.exchangeConnections.toggleLive(body),
    onSuccess: invalidate,
  });

  return { create, test, remove, toggleLive };
}
