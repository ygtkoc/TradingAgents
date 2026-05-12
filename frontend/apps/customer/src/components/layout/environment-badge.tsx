"use client";

import { Badge } from "@ta/ui";

import { useBots } from "@/lib/hooks/queries/use-bots";

/**
 * Surfaces the dominant trading mode across the user's active bots.
 *  - any active live   → red "LIVE"
 *  - else any shadow   → yellow "SHADOW"
 *  - else              → grey "PAPER"
 *
 * Backend modes per-bot remain authoritative; this is just a visual cue.
 */
export function EnvironmentBadge() {
  const { data: bots, isLoading } = useBots();

  if (isLoading) {
    return <Badge variant="outline">···</Badge>;
  }

  const active = (bots ?? []).filter((b) => b.status === "active");
  if (active.some((b) => b.mode === "live")) {
    return <Badge variant="destructive">LIVE</Badge>;
  }
  if (active.some((b) => b.mode === "shadow")) {
    return <Badge variant="warning">SHADOW</Badge>;
  }
  return <Badge variant="secondary">PAPER</Badge>;
}
