"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { supabase } from "../../supabase/client";
import { useCurrentUser } from "../queries/use-current-user";

export interface CreateBotInput {
  name:                  string;
  exchange:              "binance" | "bybit" | "coinbase";
  symbol:                string;
  mode:                  "paper" | "live";
  strategy:              "momentum" | "trend_following" | "scalping" | "mean_reversion" | "balanced";
  risk_level:            "conservative" | "moderate" | "aggressive";
  /** Risk model: 'percentage' = % of balance, 'fixed_usd' = dollar amount. */
  risk_model:            "percentage" | "fixed_usd";
  /** Risk value: 2.0 means 2% (percentage) or $2.00 (fixed_usd). */
  risk_value:            number;
  /** Risk/reward ratio: 2.0 = 1R risked → 2R target. */
  risk_reward_ratio:     number;
  max_position_size_pct: number;
  stop_loss_pct:         number;
  take_profit_pct:       number;
  trailing_stop_pct:     number | null;
  timeframe:             "1m" | "5m" | "15m" | "1h";
}

const RISK_PROFILES: Record<
  CreateBotInput["risk_level"],
  { risk_per_trade: number; max_daily: number; max_open: number }
> = {
  conservative: { risk_per_trade: 0.5, max_daily: 1.5, max_open: 1 },
  moderate:     { risk_per_trade: 1.0, max_daily: 3.0, max_open: 2 },
  aggressive:   { risk_per_trade: 2.0, max_daily: 5.0, max_open: 3 },
};

/** Candle requirements per strategy (mirrors risk.py thresholds). */
const CANDLES_REQUIRED: Record<CreateBotInput["strategy"], number> = {
  scalping:        50,
  momentum:        100,
  trend_following: 100,
  mean_reversion:  100,
  balanced:        100,
};

export function useCreateBot() {
  const qc = useQueryClient();
  const { data: user } = useCurrentUser();

  return useMutation({
    mutationFn: async (input: CreateBotInput) => {
      if (!user) throw new Error("Not authenticated");
      console.info("bots.create.start", { user_id: user.id, name: input.name, symbol: input.symbol });

      const profile = RISK_PROFILES[input.risk_level];

      // SCHEMA NOTE: the `bots` table does NOT have a `real_trading_enabled`
      // column in this database. The autonomous-bootstrap script keeps the
      // same flag in `metadata.real_trading_enabled` — we mirror that exact
      // shape so paper/live data layout stays consistent with Python writers.
      const row = {
        user_id:                   user.id,
        name:                      input.name.trim(),
        status:                    "active" as const,
        mode:                      input.mode,
        requires_manual_approval:  input.mode === "live",
        max_open_positions:        profile.max_open,
        max_position_size_pct:     input.max_position_size_pct,
        risk_per_trade_pct:        input.risk_model === "percentage" ? input.risk_value : profile.risk_per_trade,
        max_daily_loss_pct:        profile.max_daily,
        base_currency:             "USDT",
        trading_pairs:             [input.symbol],
        is_archived:               false,
        // Strategy & risk model columns (migration 0012)
        strategy_type:             input.strategy,
        risk_model:                input.risk_model,
        risk_value:                input.risk_value,
        risk_reward_ratio:         input.risk_reward_ratio,
        // Warmup tracking — seeded at create time (migration 0012)
        warmup_status:             "pending" as const,
        candles_required:          CANDLES_REQUIRED[input.strategy],
        candles_collected:         0,
        metadata: {
          created_via:           "customer_ui",
          strategy:              input.strategy,
          risk_level:            input.risk_level,
          timeframe:             input.timeframe,
          stop_loss_pct:         input.stop_loss_pct,
          take_profit_pct:       input.take_profit_pct,
          trailing_stop_pct:     input.trailing_stop_pct,
          exchange:              input.exchange,
          real_trading_enabled:  input.mode === "live",
        },
      };

      const { data, error } = await supabase
        .from("bots")
        .insert(row)
        .select("id, name, mode")
        .single();

      if (error) {
        console.error("bots.create.failed", {
          user_id: user.id,
          error,
          message: error.message,
          code:    error.code,
          hint:    error.hint,
        });
        // Friendlier messages for common failures.
        if (error.code === "42501"
            || error.message?.includes("permission denied")
            || error.message?.includes("row-level security")) {
          throw new Error(
            "RLS denied creating a bot. Apply migration "
            + "supabase/migrations/0009_user_bot_writes.sql or call the bots-create Edge Function instead.",
          );
        }
        if (/Could not find the .* column/i.test(error.message ?? "")) {
          throw new Error(
            `Schema mismatch: ${error.message}\n\n`
            + `The frontend payload for /bots/new tried to write a column that does not exist `
            + `on this database. Move that field into the bots.metadata JSON column or extend `
            + `the schema. (See use-create-bot.ts payload.)`,
          );
        }
        throw new Error(error.message || "Could not create bot");
      }
      console.info("bots.create.success", { user_id: user.id, bot_id: data.id });
      return data as { id: string; name: string; mode: "paper" | "live" };
    },
    onSuccess: (bot) => {
      void qc.invalidateQueries({ queryKey: ["bots"] });
      // No automatic redirect here — the page handles it via useEffect on success.
      return bot;
    },
  });
}
