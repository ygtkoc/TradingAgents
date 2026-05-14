"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { supabase } from "../../supabase/client";
import { useCurrentUser } from "../queries/use-current-user";

export interface UpdateBotInput {
  name?:                  string;
  strategy_type?:         string;
  risk_model?:            "percentage" | "fixed_usd";
  risk_value?:            number;
  risk_reward_ratio?:     number;
  max_position_size_pct?: number;
  risk_per_trade_pct?:    number;
  max_daily_loss_pct?:    number;
  max_open_positions?:    number;
  requires_manual_approval?: boolean;
  /** Persisted inside metadata.trading_system */
  trading_system?:        "futures_trading" | "portfolio_management";
  /** Persisted inside metadata.stop_loss_pct */
  stop_loss_pct?:         number;
  /** Persisted inside metadata.take_profit_pct */
  take_profit_pct?:       number;
  /** Persisted inside metadata.trailing_stop_pct */
  trailing_stop_pct?:     number | null;
  /** Persisted inside metadata.timeframe */
  timeframe?:             "1m" | "5m" | "15m" | "1h";
  /** Persisted inside metadata.risk_level */
  risk_level?:            "conservative" | "moderate" | "aggressive";
}

export function useUpdateBot(botId: string) {
  const qc = useQueryClient();
  const { data: user } = useCurrentUser();

  return useMutation({
    mutationFn: async (input: UpdateBotInput) => {
      if (!user) throw new Error("Not authenticated");
      console.info("bots.update.start", { user_id: user.id, bot_id: botId, input });

      // ── Separate top-level columns from metadata-only fields ──────────────
      const { stop_loss_pct, take_profit_pct, trailing_stop_pct, timeframe, risk_level, trading_system, ...colFields } = input;

      // Fetch current metadata so we can deep-merge without clobbering other keys
      const { data: current, error: fetchErr } = await supabase
        .from("bots")
        .select("metadata")
        .eq("id", botId)
        .single();
      if (fetchErr) throw new Error(fetchErr.message);

      const prevMeta = (current?.metadata ?? {}) as Record<string, unknown>;
      const metaPatch: Record<string, unknown> = { ...prevMeta };
      if (stop_loss_pct     !== undefined) metaPatch.stop_loss_pct     = stop_loss_pct;
      if (take_profit_pct   !== undefined) metaPatch.take_profit_pct   = take_profit_pct;
      if (trailing_stop_pct !== undefined) metaPatch.trailing_stop_pct = trailing_stop_pct;
      if (timeframe         !== undefined) metaPatch.timeframe         = timeframe;
      if (risk_level        !== undefined) metaPatch.risk_level        = risk_level;
      if (trading_system    !== undefined) metaPatch.trading_system    = trading_system;

      const patch: Record<string, unknown> = {
        ...colFields,
        metadata: metaPatch,
        updated_at: new Date().toISOString(),
      };

      const { data, error } = await supabase
        .from("bots")
        .update(patch)
        .eq("id", botId)
        .select("id, name, mode, status")
        .single();

      if (error) {
        console.error("bots.update.failed", { user_id: user.id, bot_id: botId, error });
        if (error.code === "42501" || error.message?.includes("row-level security")) {
          throw new Error("Permission denied. Check RLS policy for bot updates.");
        }
        if (/Could not find the .* column/i.test(error.message ?? "")) {
          throw new Error(
            `Schema mismatch: ${error.message}\n` +
            "Apply migration 0012_bot_risk_warmup_cadence.sql with: supabase db push",
          );
        }
        throw new Error(error.message || "Could not update bot");
      }

      console.info("bots.update.success", { user_id: user.id, bot_id: botId });
      return data as { id: string; name: string; mode: string; status: string };
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["bots"] });
    },
    onError: (err) => {
      console.error("bots.update.error", { user_id: user?.id, bot_id: botId, error: err });
    },
  });
}
