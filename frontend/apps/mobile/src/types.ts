export type SessionStatus = "loading" | "signed-out" | "signed-in";

export type DecisionRow = {
  id: string;
  user_id?: string | null;
  bot_id?: string | null;
  symbol: string;
  direction: string | null;
  mode: string | null;
  final_decision: string;
  approval_status: string;
  manual_approval_required?: boolean | null;
  rejection_reason?: string | null;
  approved_at?: string | null;
  score_summary: Record<string, unknown> | null;
  risk_summary?: Record<string, unknown> | null;
  security_summary?: Record<string, unknown> | null;
  metadata?: Record<string, unknown> | null;
  created_at: string;
};

export type TradeRow = {
  id: string;
  user_id?: string | null;
  bot_id?: string | null;
  trade_decision_id?: string | null;
  symbol: string;
  direction: string | null;
  mode: string | null;
  status: string;
  lifecycle_status?: string | null;
  lifecycle_error?: string | null;
  quantity?: number | string | null;
  filled_quantity?: number | string | null;
  entry_price?: number | string | null;
  avg_entry_price?: number | string | null;
  avg_fill_price?: number | string | null;
  exit_price?: number | string | null;
  stop_loss?: number | string | null;
  take_profit?: number | string | null;
  r_multiple: number | string | null;
  realized_pnl: number | string | null;
  unrealized_pnl?: number | string | null;
  pnl_pct: number | string | null;
  close_reason: string | null;
  metadata?: Record<string, unknown> | null;
  closed_at: string | null;
  created_at: string;
};

export type BotRow = {
  id: string;
  user_id?: string | null;
  name: string;
  status: string;
  mode: string | null;
  symbol: string | null;
  updated_at: string | null;
  created_at: string;
};

export type MarketMove = {
  symbol: string;
  change24h: number;
  lastPrice?: number;
};
