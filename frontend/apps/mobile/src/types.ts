export type SessionStatus = "loading" | "signed-out" | "signed-in";

export type DecisionRow = {
  id: string;
  symbol: string;
  direction: string | null;
  mode: string | null;
  final_decision: string;
  approval_status: string;
  score_summary: Record<string, unknown> | null;
  created_at: string;
};

export type TradeRow = {
  id: string;
  symbol: string;
  direction: string | null;
  mode: string | null;
  status: string;
  r_multiple: number | string | null;
  realized_pnl: number | string | null;
  pnl_pct: number | string | null;
  close_reason: string | null;
  closed_at: string | null;
  created_at: string;
};

export type BotRow = {
  id: string;
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
};
