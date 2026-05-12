/**
 * Domain types — the shapes the frontend renders.
 *
 * These mirror the read model returned by Supabase queries. Keep field names
 * identical to the database columns so direct `select()` queries deserialize
 * without manual mapping.
 *
 * NEVER mutate trades, trade_decisions, signals, agent_runs, or agent_outputs
 * from the frontend. These types are READ-ONLY for the client.
 */
import type {
  ApprovalStatus,
  BotStatus,
  ExecutionStatus,
  FinalDecision,
  LifecycleStatus,
  Severity,
  TradeDirection,
  TradeMode,
  TradeStatus,
  UserRole,
} from "./enums";

export type ISO8601 = string;
export type UUID    = string;

// ── Trade (read-only on frontend) ────────────────────────────────────────────
export interface Trade {
  id:                UUID;
  user_id:           UUID;
  bot_id:            UUID;
  trade_decision_id: UUID | null;
  agent_run_id:      UUID | null;

  exchange:    string;
  symbol:      string;
  side:        "buy" | "sell";
  direction:   TradeDirection;
  mode:        TradeMode;
  status:      TradeStatus;

  entry_price:     number;
  quantity:        number;
  filled_quantity: number | null;
  avg_fill_price:  number | null;

  stop_loss:   number | null;
  take_profit: number | null;
  exit_price:  number | null;
  avg_exit_price: number | null;

  unrealized_pnl: number | null;
  realized_pnl:   number | null;
  pnl:            number | null;

  exchange_order_id: string | null;
  close_order_id:    string | null;
  close_reason:      string | null;

  // Risk / position-sizing (migration 0011)
  risk_amount:       number | null;
  risk_percent:      number | null;
  risk_reward_ratio: number | null;
  r_multiple:        number | null;
  expected_reward:   number | null;
  notional:          number | null;

  // Lifecycle (read-only)
  lifecycle_status:           LifecycleStatus;
  lifecycle_worker_id:        string | null;
  lifecycle_claimed_at:       ISO8601 | null;
  lifecycle_last_checked_at:  ISO8601 | null;
  lifecycle_error:            string | null;
  lifecycle_retry_count:      number;
  trailing_stop_price:        number | null;
  highest_price_seen:         number | null;
  lowest_price_seen:          number | null;

  metadata:   Record<string, unknown>;
  created_at: ISO8601;
  updated_at: ISO8601 | null;
  closed_at:  ISO8601 | null;
}

// ── Trade decision (read-only on frontend) ───────────────────────────────────
export interface TradeDecision {
  id:                UUID;
  user_id:           UUID;
  bot_id:            UUID;
  agent_run_id:      UUID;
  signal_id:         UUID | null;

  exchange:        string;
  symbol:          string;
  direction:       TradeDirection;
  mode:            TradeMode;
  final_decision:  FinalDecision;
  approval_status: ApprovalStatus;

  security_summary: Record<string, unknown>;
  veto_summary:     Record<string, unknown>;
  risk_summary:     Record<string, unknown>;
  /** Score breakdown written by agent-engine: aggregated_score, confidence, reasoning. */
  score_summary?:   Record<string, unknown> | null;
  /** Snapshot of which agents ran. */
  agent_outputs_snapshot?: Record<string, unknown> | null;
  reasoning?:        string | null;
  approval_reason?:  string | null;
  rejection_reason?: string | null;
  manual_approval_required?: boolean;

  execution_status: ExecutionStatus;
  execution_error?: string | null;
  linked_trade_id:  UUID | null;
  metadata?:        Record<string, unknown> | null;
  approved_at?:     ISO8601 | null;
  approved_by?:     UUID | null;
  suggested_entry_price?: number | null;
  suggested_quantity?: number | null;
  suggested_stop_loss?: number | null;
  suggested_take_profit?: number | null;

  created_at: ISO8601;
  updated_at?: ISO8601 | null;
}

// ── Bot ──────────────────────────────────────────────────────────────────────
export interface Bot {
  id:                       UUID;
  user_id:                  UUID;
  name:                     string;
  status:                   BotStatus;
  mode:                     TradeMode;
  real_trading_enabled:     boolean;
  requires_manual_approval: boolean;
  max_open_positions:       number;
  max_position_size_pct:    number;
  risk_per_trade_pct:       number;
  max_daily_loss_pct:       number;
  base_currency:            string;
  trading_pairs:            string[];
  active_config_id:         UUID | null;
  exchange_account_id:      UUID | null;
  trailing_stop_pct:        number | null;
  is_archived:              boolean;
  metadata:                 Record<string, unknown>;
  created_at:               ISO8601;
  updated_at:               ISO8601 | null;

  // Strategy & cadence (migration 0012)
  strategy_type:    string | null;
  last_signal_at:   ISO8601 | null;
  next_signal_at:   ISO8601 | null;

  // Risk model (migration 0012)
  risk_model:          string;   // 'percentage' | 'fixed_usd'
  risk_value:          number;
  risk_reward_ratio:   number;

  // Warmup tracking (migration 0012)
  warmup_status:       string;   // 'pending' | 'warming_up' | 'ready'
  warmup_started_at:   ISO8601 | null;
  warmup_completed_at: ISO8601 | null;
  candles_collected:   number;
  candles_required:    number;
}

// ── Bot config ───────────────────────────────────────────────────────────────
export interface BotConfig {
  id:         UUID;
  bot_id:     UUID;
  user_id:    UUID;
  version:    number;
  config:     Record<string, unknown>;
  created_at: ISO8601;
}

// ── User settings ────────────────────────────────────────────────────────────
export interface UserSettings {
  user_id:                        UUID;
  trading_enabled:                boolean;
  real_trading_enabled:           boolean;
  real_trading_allowed:           boolean;
  real_trading_requires_approval: boolean;
  daily_loss_limit_usd:           number | null;
  max_concurrent_trades:          number | null;
}

// ── Exchange account (frontend reads via SAFE view; never raw key columns) ───
export interface ExchangeAccountSafe {
  id:                  UUID;
  user_id:             UUID;
  bot_id:              UUID | null;
  exchange:            string;
  label:               string | null;
  is_active:           boolean;
  can_trade:           boolean;
  can_withdraw:        boolean;
  withdrawal_detected: boolean;
  metadata:            Record<string, unknown>;
  // NOTE: encrypted_api_key, encrypted_api_secret, key_iv are NEVER exposed.
}

// ── Market snapshot ──────────────────────────────────────────────────────────
export interface MarketSnapshot {
  id:          UUID;
  exchange:    string;
  symbol:      string;
  timeframe:   string;
  open_price:  number;
  high_price:  number;
  low_price:   number;
  close_price: number;
  volume:      number;
  spread_pct:  number | null;
  captured_at: ISO8601;
}

// ── Agent run ────────────────────────────────────────────────────────────────
export interface AgentRun {
  id:               UUID;
  user_id:          UUID;
  bot_id:           UUID;
  signal_id:        UUID | null;
  status:           "pending" | "running" | "completed" | "failed" | "cancelled" | "timeout";
  started_at:       ISO8601;
  completed_at:     ISO8601 | null;
  final_decision:   FinalDecision | null;
  total_cost_usd:   number | null;
  total_tokens:     number | null;
  metadata:         Record<string, unknown>;
  trade_decision_id?: UUID | null;
  error_message?: string | null;
  duration_ms?: number | null;
}

export interface AgentOutput {
  id:           UUID;
  agent_run_id: UUID;
  agent_name?:  string | null;
  agent_definition_id?: UUID | null;
  decision?:    string | null;
  score?:       number | null;
  confidence?:  number | null;
  veto?:        boolean | null;
  reasoning?:   string | null;
  output:       Record<string, unknown>;
  error_message?: string | null;
  duration_ms?: number | null;
  cost_usd:     number | null;
  tokens:       number | null;
  created_at:   ISO8601;
}

// ── Signal ───────────────────────────────────────────────────────────────────
export interface Signal {
  id:           UUID;
  bot_id:       UUID;
  user_id:      UUID;
  exchange:     string;
  symbol:       string;
  signal_type:  string;
  payload:      Record<string, unknown>;
  created_at:   ISO8601;
}

// ── Logs ─────────────────────────────────────────────────────────────────────
export interface RiskLog {
  id:                UUID;
  user_id:           UUID | null;
  bot_id:            UUID | null;
  trade_id:          UUID | null;
  trade_decision_id: UUID | null;
  risk_type:         string;
  severity:          Severity;
  triggered:         boolean;
  message:           string;
  metadata:          Record<string, unknown>;
  created_at:        ISO8601;
}

export interface SecurityLog {
  id:         UUID;
  user_id:    UUID | null;
  event_type: string;
  severity:   Severity;
  source:     string;
  message:    string;
  metadata:   Record<string, unknown>;
  created_at: ISO8601;
}

export interface AuditLog {
  id:         UUID;
  user_id:    UUID | null;
  action:     string;
  record_id:  string | null;
  table_name: string | null;
  source:     string;
  metadata:   Record<string, unknown>;
  created_at: ISO8601;
}

// ── Trade event (lifecycle timeline) ─────────────────────────────────────────
export interface TradeEvent {
  id:                UUID;
  trade_id:          UUID | null;
  trade_decision_id: UUID | null;
  bot_id:            UUID | null;
  user_id:           UUID | null;
  event_type:        string;
  details:           Record<string, unknown>;
  /** Actual DB column name; use this on the detail page. */
  metadata:          Record<string, unknown> | null;
  created_at:        ISO8601;
}

// ── Notification ─────────────────────────────────────────────────────────────
export interface Notification {
  id:         UUID;
  user_id:    UUID;
  type:       string;
  title:      string;
  body:       string;
  read:       boolean;
  metadata:   Record<string, unknown>;
  created_at: ISO8601;
}

// ── Platform settings (admin reads this; nobody writes from frontend) ────────
export interface PlatformSettings {
  global_trading_enabled:   boolean;
  live_execution_enabled:   boolean;
  emergency_close_enabled:  boolean;
  max_allowed_slippage_pct: number;
}

// ── Auth user (Supabase) ─────────────────────────────────────────────────────
export interface AppUser {
  id:    UUID;
  email: string | null;
  role:  UserRole;
}
