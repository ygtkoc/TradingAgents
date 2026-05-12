"use client";

import { useRealtimeChannel } from "./use-realtime-channel";

export function useRealtimePlatformSettings() {
  useRealtimeChannel({
    channel: "platform-settings",
    table:   "platform_settings",
    invalidateKeys: [["platform-settings"]],
  });
}
