"use client";

import { queryKeys } from "@ta/query/keys";
import type {
  TelegramAccount,
  TelegramChatOption,
  TelegramSignalMessage,
  TelegramSignalSource,
} from "@ta/types";
import { useQuery } from "@tanstack/react-query";

import { isDemoMode } from "../../demo";
import { supabase } from "../../supabase/client";

import { useCurrentUser } from "./use-current-user";

export function useTelegramSignalSources() {
  const { data: user } = useCurrentUser();
  return useQuery<TelegramSignalSource[]>({
    queryKey: queryKeys.telegram.sources(user?.id),
    enabled: !!user,
    staleTime: 0,
    refetchInterval: 10_000,
    queryFn: async () => {
      if (isDemoMode) return [];
      const { data, error } = await supabase
        .from("telegram_signal_sources")
        .select("*")
        .order("created_at", { ascending: false });
      if (error) throw error;
      return (data ?? []) as TelegramSignalSource[];
    },
  });
}

export function useTelegramAccounts() {
  const { data: user } = useCurrentUser();
  return useQuery<TelegramAccount[]>({
    queryKey: queryKeys.telegram.accounts(user?.id),
    enabled: !!user,
    staleTime: 0,
    refetchInterval: 10_000,
    queryFn: async () => {
      if (isDemoMode) return [];
      const { data, error } = await supabase
        .from("telegram_accounts")
        .select("id,user_id,account_label,phone_hint,connection_status,last_error,last_connected_at,metadata,created_at,updated_at")
        .order("created_at", { ascending: false });
      if (error) throw error;
      return (data ?? []) as TelegramAccount[];
    },
  });
}

export function useTelegramChatOptions(accountId?: string) {
  const { data: user } = useCurrentUser();
  return useQuery<TelegramChatOption[]>({
    queryKey: queryKeys.telegram.chats(user?.id, accountId),
    enabled: !!user && !!accountId,
    staleTime: 0,
    refetchInterval: 15_000,
    queryFn: async () => {
      if (isDemoMode || !accountId) return [];
      const { data, error } = await supabase
        .from("telegram_chat_options")
        .select("*")
        .eq("telegram_account_id", accountId)
        .order("chat_title", { ascending: true });
      if (error) throw error;
      return (data ?? []) as TelegramChatOption[];
    },
  });
}

export function useTelegramSignalMessages(limit = 50) {
  const { data: user } = useCurrentUser();
  return useQuery<TelegramSignalMessage[]>({
    queryKey: queryKeys.telegram.messages(user?.id),
    enabled: !!user,
    staleTime: 0,
    refetchInterval: 5_000,
    queryFn: async () => {
      if (isDemoMode) return [];
      const { data, error } = await supabase
        .from("telegram_signal_messages")
        .select("*")
        .order("created_at", { ascending: false })
        .limit(limit);
      if (error) throw error;
      return (data ?? []) as TelegramSignalMessage[];
    },
  });
}
