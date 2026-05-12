"use client";

import { edgeFn } from "@ta/supabase/edge-functions";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useCurrentUser } from "../queries/use-current-user";

export function useExchangeMutations() {
  const qc = useQueryClient();
  const { data: user } = useCurrentUser();

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["exchange-connections", user?.id] });

  const create = useMutation({
    mutationFn: (body: { exchange: string; label: string; api_key: string; api_secret: string }) =>
      edgeFn.exchangeConnections.create(body),
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
