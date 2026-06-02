/**
 * Typed wrappers around supabase.functions.invoke().
 *
 * Every sensitive write goes through one of these. The frontend never inserts
 * or updates trading-critical tables directly — all mutations are Edge
 * Function calls.
 *
 * Each wrapper:
 *   1. Generates an idempotency key (`x-idempotency-key` header).
 *   2. Sends the typed payload.
 *   3. Returns a discriminated `EdgeFunctionResult<T>`.
 *
 * The actual EF implementations live in the BACKEND repo — these are only
 * client-side type-safe entry points.
 */
import type {
  BotsActivateRequest,
  BotsArchiveRequest,
  BotsCreateRequest,
  BotsCreateResponse,
  BotsPauseRequest,
  BotsUpdateConfigRequest,
  DecisionsApproveRequest,
  DecisionsRejectRequest,
  EdgeFunctionResult,
  ExchangeConnectionCreateRequest,
  ExchangeConnectionCreateResponse,
  ExchangeConnectionDeleteRequest,
  ExchangeConnectionTestRequest,
  ExchangeConnectionTestResponse,
  ExchangeConnectionToggleLiveRequest,
  NotificationsMarkAllReadRequest,
  NotificationsMarkReadRequest,
  PaperAccountCreateRequest,
  PaperAccountCreateResponse,
  PaperAccountPauseResponse,
  PaperAccountResetRequest,
  PaperAccountResetResponse,
  PaperAccountStartResponse,
  ExchangeAccountsCreateRequest,
  ExchangeAccountsCreateResponse,
  ExchangeAccountsRotateKeysRequest,
  ExchangeAccountsTestPermissionsRequest,
  ExchangeAccountsTestPermissionsResponse,
  PlatformSetEmergencyCloseRequest,
  PlatformSetKillSwitchRequest,
  PlatformSetLiveExecutionRequest,
  ReconciliationResolveManualRequest,
  UserSettingsUpdateRequest,
} from "@ta/types/edge-functions";

import { createBrowserClient } from "./browser";

type SupabaseClient = ReturnType<typeof createBrowserClient>;

/** Internal helper: invoke an Edge Function with idempotency + envelope. */
async function invoke<TRequest, TResponse>(
  fn:  string,
  body: TRequest,
  client?: SupabaseClient,
): Promise<EdgeFunctionResult<TResponse>> {
  const sb = client ?? createBrowserClient();
  const idempotencyKey =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

  const {
    data: { session },
    error: sessionError,
  } = await sb.auth.getSession();

  if (sessionError || !session?.access_token) {
    return {
      ok: false,
      error: {
        code: "invalid_session",
        message: "Invalid or expired session",
      },
    };
  }

  const { data, error } = await sb.functions.invoke<EdgeFunctionResult<TResponse> | TResponse>(fn, {
    body: body as Record<string, unknown>,
    headers: {
      Authorization: `Bearer ${session.access_token}`,
      "x-idempotency-key": idempotencyKey,
    },
  });

  if (error) {
    // supabase-functions-js wraps server responses in FunctionsHttpError;
    // it exposes the raw Response on `.context`. A 404 means the Edge
    // Function is missing — surface a developer-friendly hint so the UI
    // does not just show a generic "Failed to send" string.
    const ctx = (error as unknown as { context?: { status?: number; statusText?: string } }).context;
    const isNotFound = ctx?.status === 404 || ctx?.statusText === "Not Found";

    let message = error.message || "Edge Function call failed";
    let code = "edge_function_error";
    let details: Record<string, unknown> | undefined = ctx
      ? { status: ctx.status, statusText: ctx.statusText }
      : undefined;

    const response = (error as unknown as { context?: Response }).context;
    if (response && typeof response.clone === "function") {
      try {
        const payload = await response.clone().json() as {
          error?: unknown;
          message?: unknown;
          code?: unknown;
        };
        const serverMessage =
          typeof payload.error === "string"
            ? payload.error
            : typeof payload.message === "string"
              ? payload.message
              : null;
        if (serverMessage) message = serverMessage;
        if (typeof payload.code === "string") code = payload.code;
        details = { ...(details ?? {}), response: payload };
      } catch {
        // Keep the SDK-level error if the body is not JSON.
      }
    }

    if (isNotFound) {
      message =
        `Edge Function "${fn}" is not deployed.\n\n` +
        `Local dev:\n` +
        `  cd <repo-root> && supabase functions serve --no-verify-jwt\n` +
        `  (and ensure NEXT_PUBLIC_SUPABASE_URL points at http://localhost:54321 from "supabase start")\n\n` +
        `Remote:\n` +
        `  supabase functions deploy ${fn} --project-ref <ref>`;
    }
    return {
      ok: false,
      error: {
        code:    isNotFound ? "edge_function_not_deployed" : code,
        message,
        details,
      },
    };
  }
  if (!data) {
    return {
      ok: false,
      error: { code: "empty_response", message: "Edge Function returned no body" },
    };
  }
  if (
    typeof data === "object" &&
    data !== null &&
    "ok" in data &&
    typeof (data as { ok?: unknown }).ok === "boolean"
  ) {
    return data as EdgeFunctionResult<TResponse>;
  }
  return { ok: true, data: data as TResponse };
}

function toExchangeApiKeyPayload(body: ExchangeConnectionCreateRequest) {
  return {
    exchange_name:  body.exchange,
    account_label:  body.label,
    api_key:        body.api_key,
    api_secret:     body.api_secret,
    passphrase:     body.passphrase,
    testnet:        body.testnet ?? false,
  };
}

function toExchangeAccountPayload(body: { connection_id: string }) {
  return { exchange_account_id: body.connection_id };
}

// ─── Bots ────────────────────────────────────────────────────────────────────
export const bots = {
  create:        (body: BotsCreateRequest) =>
    invoke<BotsCreateRequest, BotsCreateResponse>("bots-create", body),
  activate:      (body: BotsActivateRequest) =>
    invoke<BotsActivateRequest, void>("bots-activate", body),
  pause:         (body: BotsPauseRequest) =>
    invoke<BotsPauseRequest, void>("bots-pause", body),
  stop:          (body: BotsPauseRequest) =>
    invoke<{ bot_id: string; action: "stop" }, void>("bot-control", {
      bot_id: body.bot_id,
      action: "stop",
    }),
  archive:       (body: BotsArchiveRequest) =>
    invoke<BotsArchiveRequest, void>("bots-archive", body),
  updateConfig:  (body: BotsUpdateConfigRequest) =>
    invoke<BotsUpdateConfigRequest, void>("bots-update-config", body),
};

// ─── Decisions (manual approval flow) ────────────────────────────────────────
export const decisions = {
  approve: (body: DecisionsApproveRequest) =>
    invoke<
      { trade_decision_id: string; action: "approve" },
      void
    >("manual-trade-approval", {
      trade_decision_id: body.decision_id,
      action: "approve",
    }),
  reject:  (body: DecisionsRejectRequest) =>
    invoke<
      { trade_decision_id: string; action: "reject"; rejection_reason: string },
      void
    >("manual-trade-approval", {
      trade_decision_id: body.decision_id,
      action: "reject",
      rejection_reason: body.reason,
    }),
};

// ─── Exchange accounts (server-side encryption only) ─────────────────────────
export const exchangeAccounts = {
  create: (body: ExchangeAccountsCreateRequest) =>
    invoke<ExchangeAccountsCreateRequest, ExchangeAccountsCreateResponse>(
      "exchange-accounts-create",
      body,
    ),
  rotateKeys: (body: ExchangeAccountsRotateKeysRequest) =>
    invoke<ExchangeAccountsRotateKeysRequest, void>("exchange-accounts-rotate-keys", body),
  testPermissions: (body: ExchangeAccountsTestPermissionsRequest) =>
    invoke<
      ExchangeAccountsTestPermissionsRequest,
      ExchangeAccountsTestPermissionsResponse
    >("exchange-accounts-test-permissions", body),
};

// ─── Paper account ───────────────────────────────────────────────────────────
export const paperAccount = {
  create: (body: PaperAccountCreateRequest) =>
    invoke<PaperAccountCreateRequest, PaperAccountCreateResponse>("paper-account-create", body),
  reset:  (body: PaperAccountResetRequest = {}) =>
    invoke<PaperAccountResetRequest, PaperAccountResetResponse>("paper-account-reset", body),
  start:  () =>
    invoke<Record<string, never>, PaperAccountStartResponse>("paper-account-start", {}),
  pause:  () =>
    invoke<Record<string, never>, PaperAccountPauseResponse>("paper-account-pause", {}),
};

// ─── Exchange connections (preferred names; alias of exchangeAccounts.*) ─────
export const exchangeConnections = {
  create: (body: ExchangeConnectionCreateRequest) =>
    invoke<ReturnType<typeof toExchangeApiKeyPayload>, ExchangeConnectionCreateResponse>(
      "store-exchange-api-key", toExchangeApiKeyPayload(body),
    ),
  test:   (body: ExchangeConnectionTestRequest) =>
    invoke<ReturnType<typeof toExchangeAccountPayload>, ExchangeConnectionTestResponse>(
      "exchange-health-check", toExchangeAccountPayload(body),
    ),
  delete: (body: ExchangeConnectionDeleteRequest) =>
    invoke<ReturnType<typeof toExchangeAccountPayload>, void>(
      "revoke-exchange-api-key", toExchangeAccountPayload(body),
    ),
  toggleLive: (body: ExchangeConnectionToggleLiveRequest) =>
    invoke<ExchangeConnectionToggleLiveRequest, void>(
      "exchange-connections-toggle-live", body,
    ),
};

// ─── Notifications ───────────────────────────────────────────────────────────
export const notifications = {
  markRead:    (body: NotificationsMarkReadRequest) =>
    invoke<NotificationsMarkReadRequest, void>("notifications-mark-read", body),
  markAllRead: () =>
    invoke<NotificationsMarkAllReadRequest, void>("notifications-mark-all-read", {}),
};

// ─── User settings ───────────────────────────────────────────────────────────
export const userSettings = {
  update: (body: UserSettingsUpdateRequest) =>
    invoke<UserSettingsUpdateRequest, void>("user-settings-update", body),
};

// ─── Admin operations (admin app only — re-verified server-side) ─────────────
export const platformAdmin = {
  setKillSwitch: (body: PlatformSetKillSwitchRequest) =>
    invoke<PlatformSetKillSwitchRequest, void>("platform-set-kill-switch", body),
  setLiveExecution: (body: PlatformSetLiveExecutionRequest) =>
    invoke<PlatformSetLiveExecutionRequest, void>("platform-set-live-execution", body),
  setEmergencyClose: (body: PlatformSetEmergencyCloseRequest) =>
    invoke<PlatformSetEmergencyCloseRequest, void>("platform-set-emergency-close", body),
};

export const reconciliationAdmin = {
  resolveManual: (body: ReconciliationResolveManualRequest) =>
    invoke<ReconciliationResolveManualRequest, void>("reconciliation-resolve-manual", body),
};

/** Aggregate export — `import { edgeFn } from "@ta/supabase/edge-functions"`. */
export const edgeFn = {
  bots,
  decisions,
  exchangeAccounts,
  exchangeConnections,
  notifications,
  paperAccount,
  userSettings,
  platformAdmin,
  reconciliationAdmin,
};
