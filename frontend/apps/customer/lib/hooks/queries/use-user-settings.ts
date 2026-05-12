"use client";

import { queryKeys } from "@ta/query/keys";
import type { UserSettings } from "@ta/types";
import { useQuery } from "@tanstack/react-query";

import { supabase } from "../../supabase/client";

import { useCurrentUser } from "./use-current-user";

export function useUserSettings() {
  const { data: user } = useCurrentUser();
  return useQuery<UserSettings | null>({
    queryKey: user ? queryKeys.userSettings.detail(user.id) : ["user-settings", "none"],
    enabled:  !!user,
    queryFn: async () => {
      if (!user) return null;
      const { data, error } = await supabase
        .from("user_settings")
        .select("*")
        .eq("user_id", user.id)
        .maybeSingle();
      if (error) throw error;
      return (data ?? null) as UserSettings | null;
    },
  });
}
