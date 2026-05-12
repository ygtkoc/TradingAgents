"use client";

import { ShieldAlert } from "lucide-react";

import { usePlatformSettings } from "@/lib/hooks/queries/use-platform-settings";

/**
 * Visible only when platform_settings.global_trading_enabled === false.
 * Subscribed in real time via useRealtimePlatformSettings (mounted in
 * RealtimeBridge), so toggling on the admin side updates customers instantly.
 */
export function KillSwitchBanner() {
  const { data } = usePlatformSettings();
  if (!data || data.global_trading_enabled) return null;

  return (
    <div className="flex items-center justify-center gap-2 border-b border-destructive/30 bg-destructive/15 px-4 py-2 text-[12px] font-semibold text-destructive backdrop-blur-sm">
      <ShieldAlert className="h-4 w-4" />
      <span>
        Platform trading is currently disabled by an operator. New orders will
        not be submitted.
      </span>
    </div>
  );
}
