import type { TradeDecision, FinalDecision, ApprovalStatus, ExecutionStatus, TradeMode, TradeDirection } from "@ta/types";

const SYMBOLS  = ["BTC/USDT", "ETH/USDT", "SOL/USDT"] as const;
const FINAL: FinalDecision[] = [
  "open_long",
  "open_short",
  "wait",
  "open_long",
  "manual_approval_required",
  "open_long",
  "reject",
  "open_short",
  "manual_approval_required",
  "open_long",
];
const APPROVALS: ApprovalStatus[] = [
  "auto_approved",
  "auto_approved",
  "auto_approved",
  "approved",
  "pending",
  "auto_approved",
  "rejected",
  "auto_approved",
  "pending",
  "approved",
];
const EXECUTIONS: ExecutionStatus[] = [
  "executed", "executed", "skipped", "executed",
  "executing", "executed", "skipped", "executed",
  "executing", "executed",
];

const DAY = 24 * 60 * 60 * 1000;

export const demoDecisions: TradeDecision[] = Array.from({ length: 10 }, (_, i) => {
  const symbol = SYMBOLS[i % SYMBOLS.length] as (typeof SYMBOLS)[number];
  const finalDecision: FinalDecision   = (FINAL[i] ?? "wait");
  const approval:      ApprovalStatus  = (APPROVALS[i] ?? "auto_approved");
  const execStatus:    ExecutionStatus = (EXECUTIONS[i] ?? "executed");
  const direction:     TradeDirection  = finalDecision === "open_short" ? "short" : "long";
  const mode:          TradeMode       = i % 3 === 2 ? "live" : i % 3 === 1 ? "shadow" : "paper";

  return {
    id:           "demo-decision-" + String(i + 1).padStart(3, "0"),
    user_id:      "demo-user-00000000-0000-0000-0000-000000000001",
    bot_id:       "demo-bot-00" + ((i % 3) + 1),
    agent_run_id: "demo-run-" + String(i + 1).padStart(3, "0"),
    signal_id:    null,

    exchange:        "binance",
    symbol,
    direction,
    mode,
    final_decision:  finalDecision,
    approval_status: approval,

    security_summary: { injection_detected: false, vetoed: false },
    veto_summary:     {},
    score_summary: {
      aggregated_score: Number((55 + ((i * 9) % 35)).toFixed(0)),
      confidence: Number((0.6 + ((i * 7) % 30) / 100).toFixed(2)),
      reasoning: "Demo consensus score generated for local preview mode.",
    },
    risk_summary: {
      score:      Number((0.5 + ((i * 13) % 50) / 100).toFixed(2)),
      confidence: Number((0.6 + ((i * 7) % 30) / 100).toFixed(2)),
      entry_price: 60_000,
      quantity: 0.05,
    },

    execution_status: execStatus,
    linked_trade_id:  execStatus === "executed" ? "demo-trade-" + String(i + 1).padStart(3, "0") : null,

    created_at: new Date(Date.now() - (10 - i) * DAY / 2).toISOString(),
  };
});
