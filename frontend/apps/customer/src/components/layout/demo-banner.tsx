import { isDemoMode } from "@ta/config/env";
import { Sparkles } from "lucide-react";

/**
 * Visible only when NEXT_PUBLIC_DEMO_MODE=true. Communicates that the data
 * shown is curated demo content rather than the user's real account.
 *
 * RSC-safe — no hooks; the env flag is statically inlined at build time.
 */
export function DemoBanner() {
  if (!isDemoMode) return null;
  return (
    <div className="flex items-center justify-center gap-2 bg-primary/10 px-4 py-1.5 text-xs font-medium text-primary">
      <Sparkles className="h-3.5 w-3.5" />
      <span>
        Demo mode — showing synthetic data. Set
        {" "}<code className="rounded bg-background/60 px-1 font-mono">NEXT_PUBLIC_DEMO_MODE=false</code>
        {" "}and connect Supabase to see real data.
      </span>
    </div>
  );
}
