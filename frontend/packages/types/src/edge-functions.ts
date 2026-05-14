/**
 * Edge Function request/response shapes.
 *
 * Every sensitive write goes through one of these. Both client (UX) and
 * server (security) validate against the matching Zod schema in
 * `@ta/schemas/edge-functions`.
 */

// ─── Bots ────────────────────────────────────────────────────────────────────
export interface BotsCreateRequest {
  name:                     string;
  mode:                     "paper" | "shadow" | "live";
  exchange_account_id:      string | null;
  trading_pairs:            string[];
  max_open_positions:       number;
  max_position_size_pct:    number;
  risk_per_trade_pct:       number;
  max_daily_loss_pct:       number;
  base_currency:            string;
  requires_manual_approval: boolean;
  trailing_stop_pct?:       number | null;
}
export interface BotsCreateResponse { bot_id: string }

export interface BotsActivateRequest { bot_id: string }
export interface BotsPauseRequest    { bot_id: string }
export interface BotsArchiveRequest  { bot_id: string }
export interface BotsUpdateConfigRequest {
  bot_id: string;
  config: Record<string, unknown>;
}

// ─── Decisions ───────────────────────────────────────────────────────────────
export interface DecisionsApproveRequest { decision_id: string }
export interface DecisionsRejectRequest  { decision_id: string; reason: string }

// ─── Exchange accounts ───────────────────────────────────────────────────────
export interface ExchangeAccountsCreateRequest {
  exchange:   string;
  label:      string;
  api_key:    string;
  api_secret: string;
}
export interface ExchangeAccountsCreateResponse { account_id: string }

export interface ExchangeAccountsRotateKeysRequest {
  account_id: string;
  api_key:    string;
  api_secret: string;
}

export interface ExchangeAccountsTestPermissionsRequest {
  account_id: string;
}
export interface ExchangeAccountsTestPermissionsResponse {
  can_trade:    boolean;
  can_withdraw: boolean;
  is_safe:      boolean;
}

// ─── User settings ───────────────────────────────────────────────────────────
export interface UserSettingsUpdateRequest {
  trading_enabled?:        boolean;
  daily_loss_limit_usd?:   number | null;
  max_concurrent_trades?:  number | null;
}

// ─── Paper account ───────────────────────────────────────────────────────────
export interface PaperAccountCreateRequest  { starting_balance: number; currency?: string }
export interface PaperAccountCreateResponse { account_id: string; starting_balance: number; balance: number; status: string }

export interface PaperAccountResetRequest   { starting_balance?: number }
export interface PaperAccountResetResponse  {
  account_id: string;
  starting_balance: number;
  status?: "paused";
  deleted: { signals: number; decisions: number; trades: number; events: number; account_events: number };
}

export interface PaperAccountStartResponse  { account_id: string; status: "active" }
export interface PaperAccountPauseResponse  { account_id: string; status: "paused" }

// ─── Exchange connections (alias of exchangeAccounts.* for clarity) ───────────
export interface ExchangeConnectionCreateRequest  {
  exchange:   string;
  label:      string;
  api_key:    string;
  api_secret: string;
}
export interface ExchangeConnectionCreateResponse { connection_id: string }

export interface ExchangeConnectionTestRequest    { connection_id: string }
export interface ExchangeConnectionTestResponse   {
  can_trade: boolean;
  can_withdraw: boolean;
  is_safe: boolean;
}

export interface ExchangeConnectionDeleteRequest      { connection_id: string }
export interface ExchangeConnectionToggleLiveRequest  { connection_id: string; enable: boolean; risk_acknowledged: boolean }

// ─── Notifications ───────────────────────────────────────────────────────────
export interface NotificationsMarkReadRequest {
  notification_ids: string[];
}
export type NotificationsMarkAllReadRequest = Record<string, never>;

// ─── Admin: platform ─────────────────────────────────────────────────────────
export interface PlatformSetKillSwitchRequest    { enabled: boolean; reason: string }
export interface PlatformSetLiveExecutionRequest { enabled: boolean }
export interface PlatformSetEmergencyCloseRequest{ enabled: boolean }

// ─── Admin: reconciliation ───────────────────────────────────────────────────
export interface ReconciliationResolveManualRequest {
  trade_id: string;
  action:   "mark_closed" | "mark_failed" | "reset_to_idle";
  reason:   string;
}

// ─── Common envelope ─────────────────────────────────────────────────────────
export interface EdgeFunctionError {
  code:    string;
  message: string;
  details?: Record<string, unknown>;
}

export type EdgeFunctionResult<T> =
  | { ok: true;  data: T }
  | { ok: false; error: EdgeFunctionError };
