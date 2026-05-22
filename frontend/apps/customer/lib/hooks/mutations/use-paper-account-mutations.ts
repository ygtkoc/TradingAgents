"use client";

import { allowDevDirectPaperAccountWrite, isDevelopment } from "@ta/config/env";
import { edgeFn } from "@ta/supabase/edge-functions";
import type { EdgeFunctionResult } from "@ta/types";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { supabase } from "../../supabase/client";
import { useCurrentUser } from "../queries/use-current-user";

/**
 * Heuristic: did the wrapper come back with a "function unreachable" error
 * vs a valid backend rejection?
 *
 * We match a broad set of patterns because Supabase-js surfaces EF failures
 * differently depending on: whether the local relay is up, whether the
 * specific function is deployed, and which version of the client is used.
 *
 * In dev mode with allowDevDirectPaperAccountWrite=true we also treat ANY
 * unrecognised error as unreachable so the fallback is always attempted —
 * the caller passes `permissiveInDev=true` for this behaviour.
 */
function isFunctionUnreachable(err: unknown, permissiveInDev = false): boolean {
  if (!err) return false;

  // Check the error code on envelope objects (EdgeFunctionResult.error.code).
  const code = (err as { code?: string }).code ?? "";
  if (code === "edge_function_not_deployed" || code === "edge_function_error") return true;

  const msg = (err as Error).message ?? String(err);
  const matched = (
    /Edge Function .* is not deployed/i.test(msg) ||
    /edge function not found/i.test(msg) ||
    /Failed to send a request to the Edge Function/i.test(msg) ||
    /FunctionsRelayError/i.test(msg) ||
    /FunctionsFetchError/i.test(msg) ||
    /FunctionsHttpError/i.test(msg) ||
    /NetworkError/i.test(msg) ||
    /Failed to fetch/i.test(msg) ||
    /fetch failed/i.test(msg) ||
    /ECONNREFUSED/i.test(msg) ||
    /Load failed/i.test(msg)
  );

  // In dev mode with the escape hatch flag, any unrecognised error also
  // triggers the fallback so developers are never silently blocked.
  return matched || permissiveInDev;
}

const DEPLOY_HINT =
  "Deploy:\n" +
  "  supabase functions deploy paper-account-create paper-account-reset \\\n" +
  "                            paper-account-start  paper-account-pause\n\n" +
  "Or serve locally:\n" +
  "  supabase functions serve --no-verify-jwt\n\n" +
  "Or enable the dev fallback (development only):\n" +
  "  NEXT_PUBLIC_ALLOW_DEV_DIRECT_PAPER_ACCOUNT_WRITE=true";

/**
 * Unwraps the `EdgeFunctionResult` envelope. When the Edge Function returns
 * `{ ok: false, error }`, this throws so React Query reports a real `error`
 * to the UI — otherwise the mutation looks successful even though the
 * backend rejected it (which was the prior failure mode for /paper).
 */
async function unwrap<T>(p: Promise<EdgeFunctionResult<T> | T>): Promise<T> {
  const res = await p;
  if (
    typeof res === "object" &&
    res !== null &&
    "ok" in res &&
    typeof (res as { ok?: unknown }).ok === "boolean"
  ) {
    const envelope = res as EdgeFunctionResult<T>;
    if (envelope.ok) return envelope.data;
    throw new Error(envelope.error.message || "Edge Function call failed");
  }
  return res as T;
}

export function usePaperAccountMutations() {
  const qc = useQueryClient();
  const { data: user } = useCurrentUser();

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["paper-account",        user?.id] });
    void qc.invalidateQueries({ queryKey: ["paper-account-events", user?.id] });
    void qc.invalidateQueries({ queryKey: ["trades"] });
    void qc.invalidateQueries({ queryKey: ["decisions"] });
  };

  const create = useMutation({
    mutationFn: async (startingBalance: number) => {
      // ── Evaluate dev-fallback conditions ────────────────────────────────
      // IMPORTANT: use process.env literals directly so Next.js inlines the
      // correct value at bundle time. The imported `allowDevDirectPaperAccountWrite`
      // constant can be stale if the dev server was started before the env var
      // was added to .env.local (module-level constants are frozen at boot).
      const devFlagRaw  = process.env.NEXT_PUBLIC_ALLOW_DEV_DIRECT_PAPER_ACCOUNT_WRITE;
      const appEnvRaw   = process.env.NEXT_PUBLIC_APP_ENV;
      const devFlagOn   = devFlagRaw === "true" || devFlagRaw === "1";
      const isDevEnv    = appEnvRaw === "development";
      const fallbackOk  = devFlagOn && isDevEnv;

      // paper.create.env — emitted first so any mis-configuration is visible
      // in the browser console before any network call is attempted.
      console.info("paper.create.env", {
        NEXT_PUBLIC_APP_ENV:                               appEnvRaw,
        NEXT_PUBLIC_ALLOW_DEV_DIRECT_PAPER_ACCOUNT_WRITE: devFlagRaw,
        dev_fallback_eligible: fallbackOk,
        // imported module values (may differ if env changed after server start)
        imported_isDevelopment:                isDevelopment,
        imported_allowDevDirectPaperAccountWrite: allowDevDirectPaperAccountWrite,
      });

      let efErr: unknown = null;

      // ── Try Edge Function first ──────────────────────────────────────────
      // paper.create.edge — emitted before and after the EF call so you can
      // see exactly where a hang or timeout occurs.
      console.info("paper.create.edge", { phase: "attempt", user_id: user?.id });
      try {
        const result = await unwrap(
          edgeFn.paperAccount.create({ starting_balance: startingBalance }),
        );
        console.info("paper.create.edge", { phase: "success", user_id: user?.id });
        return result;
      } catch (err) {
        efErr = err;
        console.warn("paper.create.edge", {
          phase:                "failed",
          user_id:              user?.id,
          error_message:        (err as Error)?.message ?? String(err),
          dev_fallback_eligible: fallbackOk,
        });
      }

      // ── Dev-only direct-write fallback ───────────────────────────────────
      // When the Edge Function is unreachable (not deployed / not served locally)
      // AND the developer has opted in via NEXT_PUBLIC_ALLOW_DEV_DIRECT_PAPER_ACCOUNT_WRITE=true,
      // write the paper_accounts row directly via the authenticated Supabase client.
      //
      // Requirements:
      //   • Migration 0010 applied (INSERT + UPDATE RLS for authenticated users)
      //   • User is signed in
      if (fallbackOk) {
        if (!user?.id) {
          throw new Error("Not signed in. Please sign in before creating a paper account.");
        }

        // paper.create.dev_fallback — emitted when bypass is triggered so
        // developers can confirm the fallback path is actually running.
        console.warn("paper.create.dev_fallback", {
          phase:    "attempt",
          user_id:  user.id,
          ef_error: (efErr as Error)?.message,
        });

        const nowIso = new Date().toISOString();
        const { data, error } = await supabase
          .from("paper_accounts")
          .upsert(
            {
              user_id:          user.id,
              currency:         "USD",
              starting_balance: startingBalance,
              balance:          startingBalance,
              reserved_balance: 0,
              status:           "active",
              started_at:       nowIso,
              paused_at:        null,
              metadata:         { created_via: "customer_dev_fallback" },
            },
            { onConflict: "user_id" },
          )
          .select("id, balance, status, starting_balance")
          .single();

        if (error) {
          console.error("paper.create.dev_fallback", {
            phase:   "denied",
            user_id: user.id,
            code:    error.code,
            message: error.message,
          });

          // Surface an actionable error with both the EF and RLS failure.
          const efMsg = efErr ? `\nEdge Function error: ${(efErr as Error).message}\n` : "";
          throw new Error(
            `Paper account creation failed.\n` +
            `${efMsg}\n` +
            `Dev fallback denied by RLS (code ${error.code}): ${error.message}\n\n` +
            `To fix:\n` +
            `  1. Apply migration 0010_paper_accounts_authenticated_access.sql:\n` +
            `       supabase db push\n` +
            `  2. OR deploy the Edge Function:\n` +
            `       supabase functions serve --no-verify-jwt\n\n` +
            DEPLOY_HINT,
          );
        }

        console.info("paper.create.dev_fallback", {
          phase:      "success",
          user_id:    user.id,
          account_id: data.id,
        });
        return {
          account_id:       data.id,
          starting_balance: Number(data.starting_balance),
          balance:          Number(data.balance),
          status:           data.status as "active" | "paused" | "inactive",
        };
      }

      // ── Not in dev fallback mode → re-throw with deploy hint ─────────────
      const unreachable = isFunctionUnreachable(efErr);
      if (unreachable) {
        throw new Error(
          ((efErr as Error).message ?? "Edge Function unreachable") +
          "\n\n" +
          DEPLOY_HINT,
        );
      }
      throw efErr;
    },
    onError: (error) => {
      console.error("paper_account.create.failed", {
        user_id: user?.id,
        error,
      });
    },
    onSuccess: invalidate,
  });

  // ── Shared dev-fallback helper ─────────────────────────────────────────────
  // Re-evaluates env vars inline so Next.js inlines the correct literals.
  const _devFallbackOk = () =>
    process.env.NEXT_PUBLIC_ALLOW_DEV_DIRECT_PAPER_ACCOUNT_WRITE === "true" &&
    process.env.NEXT_PUBLIC_APP_ENV === "development";

  const reset = useMutation({
    mutationFn: async (startingBalance?: number) => {
      if (!user?.id) throw new Error("Not signed in.");
      const requestedBalance = Number(startingBalance);
      const newStartingBalance =
        Number.isFinite(requestedBalance) && requestedBalance > 0
          ? requestedBalance
          : undefined;
      console.info("paper.reset.start", { user_id: user.id, starting_balance: newStartingBalance });

      let efErr: unknown = null;
      try {
        const result = await unwrap(
          edgeFn.paperAccount.reset(
            newStartingBalance != null ? { starting_balance: newStartingBalance } : {},
          ),
        );
        console.info("paper.reset.edge", { phase: "success", user_id: user.id, summary: result });
        return result;
      } catch (err) {
        efErr = err;
        console.warn("paper.reset.edge", {
          phase: "failed",
          user_id: user.id,
          error_message: (err as Error)?.message ?? String(err),
        });
      }

      // ── Try paper_reset() RPC first (works in dev + prod with authenticated client).
      // The function is SECURITY DEFINER + GRANT to authenticated, so no service_role needed.
      const { data: rpcData, error: rpcErr } = await (supabase as any)
        .rpc("paper_reset", {
          p_user_id: user.id,
          p_starting_balance: newStartingBalance ?? null,
        });

      if (!rpcErr) {
        console.info("paper.reset.success", { user_id: user.id, summary: rpcData });
        return rpcData;
      }

      // ── RPC failed (function not deployed yet) → dev direct fallback ─────
      // Do not do a partial direct-write reset. A successful reset must come
      // from the RPC so paper runtime data and account state clear together.
      console.warn("paper.reset.rpc_failed", {
        user_id: user.id,
        code: rpcErr.code,
        message: rpcErr.message,
      });

      throw new Error(
        `Paper reset failed: ${rpcErr.message}\n\n` +
        `Edge Function error: ${(efErr as Error)?.message ?? String(efErr)}\n\n` +
        "A safe reset must clear paper-mode signals, decisions, trades, lifecycle events, and account events atomically. Deploy/serve the reset backend first:\n" +
        "  supabase db push\n" +
        "  supabase functions serve --no-verify-jwt\n\n" +
        "Required migration: supabase/migrations/0016_harden_paper_reset_scope.sql",
      );
    },
    onSuccess: () => {
      console.info("paper.reset", { user_id: user?.id });
      invalidate();
    },
    onError: (err) => console.error("paper.reset.failed", { user_id: user?.id, error: err }),
  });

  const closeOpen = useMutation({
    mutationFn: async () => {
      if (!user?.id) throw new Error("Not signed in.");
      const { data, error } = await (supabase as any)
        .rpc("paper_close_open_trades", { p_user_id: user.id });
      if (error) {
        throw new Error(
          `Open paper positions could not be closed: ${error.message}\n\n` +
          "Deploy the latest database migration first:\n" +
          "  supabase db push\n\n" +
          "Required migration: supabase/migrations/0017_paper_close_reason_and_close_all.sql",
        );
      }
      return data as { ok: boolean; closed: number; balance: number; realized_pnl: number };
    },
    onSuccess: invalidate,
    onError: (err) => console.error("paper.close_open.failed", { user_id: user?.id, error: err }),
  });

  const start = useMutation({
    mutationFn: async () => {
      const devOk = _devFallbackOk();
      console.info("paper.start.env", { dev_fallback_eligible: devOk });

      let efErr: unknown = null;
      console.info("paper.start.edge", { phase: "attempt" });
      try {
        const result = await unwrap(edgeFn.paperAccount.start());
        console.info("paper.start.edge", { phase: "success" });
        return result;
      } catch (err) {
        efErr = err;
        console.warn("paper.start.edge", {
          phase: "failed",
          error_message: (err as Error)?.message ?? String(err),
          dev_fallback_eligible: devOk,
        });
      }

      if (devOk && user?.id) {
        console.warn("paper.start.dev_fallback", { phase: "attempt", user_id: user.id });
        const { data, error } = await supabase
          .from("paper_accounts")
          .update({ status: "active", started_at: new Date().toISOString(), paused_at: null })
          .eq("user_id", user.id)
          .select("id, status")
          .single();

        if (error) {
          console.error("paper.start.dev_fallback", {
            phase: "denied", user_id: user.id, code: error.code, message: error.message,
          });
          throw new Error(`Paper start failed. Dev fallback denied: ${error.message}`);
        }
        console.info("paper.start.dev_fallback", { phase: "success", user_id: user.id });
        return { account_id: data.id, status: "active" as const };
      }

      throw efErr;
    },
    onSuccess: invalidate,
    onError: (err) => console.error("paper.start.failed", { user_id: user?.id, error: err }),
  });

  const pause = useMutation({
    mutationFn: async () => {
      const devOk = _devFallbackOk();
      console.info("paper.pause.env", { dev_fallback_eligible: devOk });

      let efErr: unknown = null;
      console.info("paper.pause.edge", { phase: "attempt" });
      try {
        const result = await unwrap(edgeFn.paperAccount.pause());
        console.info("paper.pause.edge", { phase: "success" });
        return result;
      } catch (err) {
        efErr = err;
        console.warn("paper.pause.edge", {
          phase: "failed",
          error_message: (err as Error)?.message ?? String(err),
          dev_fallback_eligible: devOk,
        });
      }

      if (devOk && user?.id) {
        console.warn("paper.pause.dev_fallback", { phase: "attempt", user_id: user.id });
        const { data, error } = await supabase
          .from("paper_accounts")
          .update({ status: "paused", paused_at: new Date().toISOString() })
          .eq("user_id", user.id)
          .select("id, status")
          .single();

        if (error) {
          console.error("paper.pause.dev_fallback", {
            phase: "denied", user_id: user.id, code: error.code, message: error.message,
          });
          throw new Error(`Paper pause failed. Dev fallback denied: ${error.message}`);
        }
        console.info("paper.pause.dev_fallback", { phase: "success", user_id: user.id });
        return { account_id: data.id, status: "paused" as const };
      }

      throw efErr;
    },
    onSuccess: invalidate,
    onError: (err) => console.error("paper.pause.failed", { user_id: user?.id, error: err }),
  });

  return { create, reset, start, pause, closeOpen };
}
