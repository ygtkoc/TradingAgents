"use client";

import { useRealtimePendingDecisions } from "@/lib/hooks/realtime/use-realtime-decisions";
import { useRealtimeNotifications } from "@/lib/hooks/realtime/use-realtime-notifications";
import { useRealtimePlatformSettings } from "@/lib/hooks/realtime/use-realtime-platform-settings";
import { useRealtimeOpenTrades } from "@/lib/hooks/realtime/use-realtime-trades";

/**
 * Mount once at the app shell. Wires every shell-level realtime channel
 * into React Query invalidation. Renders nothing.
 */
export function RealtimeBridge() {
  useRealtimeOpenTrades();
  useRealtimePendingDecisions();
  useRealtimeNotifications();
  useRealtimePlatformSettings();
  return null;
}
