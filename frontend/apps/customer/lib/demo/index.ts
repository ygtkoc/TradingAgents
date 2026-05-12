/**
 * Demo / test mode helpers.
 *
 *   - `isDemoMode` is true when NEXT_PUBLIC_DEMO_MODE=true. In that case the
 *     app shell skips auth, hooks return demo data, realtime is disabled,
 *     and a banner indicates the synthetic state.
 *
 *   - `withDemoFallback(real, demo)` returns demo ONLY when `isDemoMode` is
 *     true. Otherwise it always returns the real array — even if empty —
 *     so the UI can render a real empty state. NO fake data leaks into a
 *     production-like UI.
 *
 *   - `DEMO_USER` is the synthetic AppUser injected when demo mode is on.
 */
import { isDemoMode as isDemoModeFlag } from "@ta/config/env";
import type { AppUser } from "@ta/types";

export const isDemoMode: boolean = isDemoModeFlag;

export const DEMO_USER: AppUser = {
  id:    "demo-user-00000000-0000-0000-0000-000000000001",
  email: "demo@tradingagents.local",
  role:  "user",
};

/**
 * Demo data is shown ONLY when `NEXT_PUBLIC_DEMO_MODE=true`.
 *
 * Outside demo mode, the real array is returned verbatim — including when
 * empty — so the UI surfaces a real "no data yet" state and never invents
 * trades / decisions / bots / balances.
 */
export function withDemoFallback<T>(real: T[], demo: T[]): T[] {
  if (isDemoMode) return demo;
  return real;
}
