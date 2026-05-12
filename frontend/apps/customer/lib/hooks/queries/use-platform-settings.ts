"use client";

import { queryKeys } from "@ta/query/keys";
import type { PlatformSettings } from "@ta/types";
import { useQuery } from "@tanstack/react-query";

import { supabase } from "../../supabase/client";

interface PlatformSettingRow {
  key:   string;
  value: unknown;
}

const DEFAULTS: PlatformSettings = {
  global_trading_enabled:   true,
  live_execution_enabled:   false,
  emergency_close_enabled:  true,
  max_allowed_slippage_pct: 1.0,
};

function parseRows(rows: PlatformSettingRow[]): PlatformSettings {
  const out: PlatformSettings = { ...DEFAULTS };
  for (const r of rows) {
    if (r.key === "global_trading_enabled")   out.global_trading_enabled   = Boolean(r.value);
    else if (r.key === "live_execution_enabled")   out.live_execution_enabled   = Boolean(r.value);
    else if (r.key === "emergency_close_enabled")  out.emergency_close_enabled  = Boolean(r.value);
    else if (r.key === "max_allowed_slippage_pct") out.max_allowed_slippage_pct = Number(r.value) || DEFAULTS.max_allowed_slippage_pct;
  }
  return out;
}

export function usePlatformSettings() {
  return useQuery<PlatformSettings>({
    queryKey: ["platform-settings"],
    staleTime: 30_000,
    queryFn: async () => {
      const { data, error } = await supabase
        .from("platform_settings")
        .select("key,value");
      if (error) {
        // RLS may block this for users — fall back to safe defaults silently.
        return DEFAULTS;
      }
      return parseRows((data ?? []) as PlatformSettingRow[]);
    },
  });
}
