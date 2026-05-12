"use client";

import type { ExchangeAccountSafe } from "@ta/types";
import { useQuery } from "@tanstack/react-query";

import { supabase } from "../../supabase/client";
import { useCurrentUser } from "./use-current-user";

/**
 * Reads `exchange_accounts` columns that are SAFE for the frontend.
 * NEVER selects encrypted_api_key / encrypted_api_secret / key_iv.
 */
export function useExchangeConnections() {
  const { data: user } = useCurrentUser();
  return useQuery<ExchangeAccountSafe[]>({
    queryKey: ["exchange-connections", user?.id],
    enabled:  !!user,
    queryFn: async () => {
      const { data, error } = await supabase
        .from("exchange_accounts")
        .select("id,user_id,bot_id,exchange,label,is_active,can_trade,can_withdraw,withdrawal_detected,metadata")
        .eq("user_id", user!.id)
        .order("created_at", { ascending: false });
      if (error) throw error;
      return (data ?? []) as ExchangeAccountSafe[];
    },
  });
}
