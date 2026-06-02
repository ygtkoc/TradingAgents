import { NextResponse, type NextRequest } from "next/server";

import { env } from "@ta/config/env";
import { createServerClient } from "@ta/supabase/server";
import type {
  EdgeFunctionResult,
  ExchangeConnectionCreateResponse,
} from "@ta/types/edge-functions";

type CreateExchangeConnectionBody = {
  exchange: string;
  label: string;
  api_key: string;
  api_secret: string;
  passphrase?: string;
  testnet?: boolean;
};

function edgePayload(body: CreateExchangeConnectionBody) {
  return {
    exchange_name: body.exchange,
    account_label: body.label,
    api_key: body.api_key,
    api_secret: body.api_secret,
    passphrase: body.passphrase,
    testnet: body.testnet ?? false,
  };
}

function errorResult(
  code: string,
  message: string,
  details?: Record<string, unknown>,
): EdgeFunctionResult<ExchangeConnectionCreateResponse> {
  return { ok: false, error: { code, message, details } };
}

export async function POST(request: NextRequest) {
  let body: CreateExchangeConnectionBody;
  try {
    body = (await request.json()) as CreateExchangeConnectionBody;
  } catch {
    return NextResponse.json(errorResult("bad_request", "Invalid request body"), {
      status: 400,
    });
  }

  if (!body.exchange || !body.label || !body.api_key || !body.api_secret) {
    return NextResponse.json(
      errorResult("bad_request", "Exchange, label, API key and API secret are required"),
      { status: 400 },
    );
  }

  const supabase = createServerClient();
  const {
    data: { session },
    error: sessionError,
  } = await supabase.auth.getSession();

  if (sessionError || !session?.access_token) {
    return NextResponse.json(
      errorResult(
        "invalid_session",
        "Your session could not be refreshed. Please sign in again and retry.",
      ),
      { status: 401 },
    );
  }

  const idempotencyKey =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

  const edgeResponse = await fetch(
    `${env.NEXT_PUBLIC_SUPABASE_URL}/functions/v1/store-exchange-api-key`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${session.access_token}`,
        apikey: env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
        "x-idempotency-key": idempotencyKey,
      },
      body: JSON.stringify(edgePayload(body)),
    },
  );

  let payload: unknown = null;
  try {
    payload = await edgeResponse.json();
  } catch {
    // Keep payload null and return a structured error below.
  }

  if (!edgeResponse.ok) {
    const responsePayload =
      payload && typeof payload === "object" ? (payload as Record<string, unknown>) : {};
    const serverMessage =
      typeof responsePayload.error === "string"
        ? responsePayload.error
        : typeof responsePayload.message === "string"
          ? responsePayload.message
          : "Exchange connection failed";
    const serverCode =
      typeof responsePayload.code === "string"
        ? responsePayload.code
        : "edge_function_error";

    return NextResponse.json(
      errorResult(serverCode, serverMessage, {
        status: edgeResponse.status,
        response: responsePayload,
      }),
      { status: edgeResponse.status },
    );
  }

  return NextResponse.json({ ok: true, data: payload });
}
