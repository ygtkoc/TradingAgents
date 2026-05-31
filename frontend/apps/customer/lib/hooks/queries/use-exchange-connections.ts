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
        .select(
          [
            "id",
            "user_id",
            "exchange_name",
            "account_label",
            "connection_status",
            "can_read",
            "can_trade",
            "can_withdraw",
            "withdrawal_detected",
            "last_health_check_at",
            "last_health_status",
            "health_error_message",
            "ip_whitelist_configured",
            "testnet",
            "is_active",
            "metadata",
          ].join(","),
        )
        .eq("user_id", user!.id)
        .order("created_at", { ascending: false });
      if (error) throw error;
      return (data ?? []) as unknown as ExchangeAccountSafe[];
    },
  });
}
