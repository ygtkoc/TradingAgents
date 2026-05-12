"use client";

import { queryKeys } from "@ta/query/keys";
import { useQuery } from "@tanstack/react-query";

import { DEMO_USER, isDemoMode } from "../../demo";
import { supabase } from "../../supabase/client";

export interface CurrentUser {
  id:    string;
  email: string | null;
  role:  "user" | "admin";
}

export function useCurrentUser() {
  return useQuery<CurrentUser | null>({
    queryKey: queryKeys.auth.user(),
    queryFn:  async () => {
      if (isDemoMode) return DEMO_USER;
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) return null;
      const rawRole = (user.app_metadata?.role as string | undefined) ?? "user";
      return {
        id:    user.id,
        email: user.email ?? null,
        role:  rawRole === "admin" ? "admin" : "user",
      };
    },
    staleTime: 60_000,
  });
}
