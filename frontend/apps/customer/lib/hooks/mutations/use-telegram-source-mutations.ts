"use client";

import { queryKeys } from "@ta/query/keys";
import type { TelegramSignalSource } from "@ta/types";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { supabase } from "../../supabase/client";
import { useCurrentUser } from "../queries/use-current-user";

const db = supabase as any;

export type TelegramSourceCreateInput = Pick<
  TelegramSignalSource,
  | "bot_id"
  | "telegram_account_id"
  | "chat_id"
  | "chat_title"
  | "topic_id"
  | "topic_title"
  | "exchange"
  | "execution_policy"
  | "require_stop_loss"
  | "max_signal_age_minutes"
  | "min_parse_confidence"
  | "signal_template"
  | "template_similarity_threshold"
>;

const autonomousUrl =
  process.env.NEXT_PUBLIC_AUTONOMOUS_URL?.replace(/\/$/, "") || "http://localhost:9090";

export function useTelegramSourceMutations() {
  const qc = useQueryClient();
  const { data: user } = useCurrentUser();

  const invalidate = async () => {
    await qc.invalidateQueries({ queryKey: queryKeys.telegram.sources(user?.id) });
  };

  const create = useMutation({
    mutationFn: async (input: TelegramSourceCreateInput) => {
      if (!user) throw new Error("Not signed in");
      const { error } = await db.from("telegram_signal_sources").insert({
        ...input,
        user_id: user.id,
        enabled: true,
        max_leverage: null,
        default_leverage: null,
        symbol_allowlist: [],
      });
      if (error) throw error;
    },
    onSuccess: invalidate,
  });

  const toggle = useMutation({
    mutationFn: async ({ id, enabled }: { id: string; enabled: boolean }) => {
      const { error } = await db
        .from("telegram_signal_sources")
        .update({ enabled })
        .eq("id", id);
      if (error) throw error;
    },
    onSuccess: invalidate,
  });

  const startAuth = useMutation({
    mutationFn: async (input: { phone_number: string; account_label: string }) => {
      if (!user) throw new Error("Not signed in");
      const res = await fetch(`${autonomousUrl}/telegram/auth/start`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ ...input, user_id: user.id }),
      });
      const json = await res.json();
      if (!res.ok || !json.ok) throw new Error(json.error || "Telegram auth failed");
      return json as { ok: true; account_id: string; phone_hint: string };
    },
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: queryKeys.telegram.accounts(user?.id) });
    },
  });

  const verifyAuth = useMutation({
    mutationFn: async (input: {
      account_id: string;
      phone_number: string;
      code: string;
      password?: string;
    }) => {
      if (!user) throw new Error("Not signed in");
      const res = await fetch(`${autonomousUrl}/telegram/auth/verify`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ ...input, user_id: user.id }),
      });
      const json = await res.json();
      if (!res.ok || !json.ok) throw new Error(json.error || "Telegram verify failed");
      return json as { ok: true; account_id: string };
    },
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: queryKeys.telegram.accounts(user?.id) });
    },
  });

  const refreshChats = useMutation({
    mutationFn: async (input: { account_id: string }) => {
      if (!user) throw new Error("Not signed in");
      const res = await fetch(`${autonomousUrl}/telegram/chats`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ ...input, user_id: user.id }),
      });
      const json = await res.json();
      if (!res.ok || !json.ok) throw new Error(json.error || "Telegram chats refresh failed");
      return json as { ok: true; chats: unknown[] };
    },
    onSuccess: async (_data, vars) => {
      await qc.invalidateQueries({ queryKey: queryKeys.telegram.chats(user?.id, vars.account_id) });
    },
  });

  return { create, toggle, startAuth, verifyAuth, refreshChats };
}
