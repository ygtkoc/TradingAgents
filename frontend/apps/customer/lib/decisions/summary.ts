import type { TradeDecision } from "@ta/types";

type SummaryLike = Record<string, unknown> | null | undefined;
type ConfidenceValue = number | string | null;

function num(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function text(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function pickNumber(summary: SummaryLike, ...keys: string[]): number | null {
  if (!summary) return null;
  for (const key of keys) {
    const value = num(summary[key]);
    if (value !== null) return value;
  }
  return null;
}

function pickText(summary: SummaryLike, ...keys: string[]): string | null {
  if (!summary) return null;
  for (const key of keys) {
    const value = text(summary[key]);
    if (value !== null) return value;
  }
  return null;
}

function formatPercentish(value: number | null): string {
  if (value === null) return "N/A";
  if (Math.abs(value) <= 1) return `${(value * 100).toFixed(0)}%`;
  if (Math.abs(value) <= 100) return `${value.toFixed(0)}%`;
  return `${value.toFixed(1)}%`;
}

function logMetric(
  type: "score" | "confidence",
  decision: TradeDecision,
  source: string | null,
  value: ConfidenceValue,
) {
  const payload = {
    decision_id: decision.id,
    signal_id: decision.signal_id,
    source,
    value,
  };

  if (value === null) {
    console.info(`decision.${type}.missing`, payload);
  } else {
    console.info(`decision.${type}.loaded`, payload);
  }
}

export function getDecisionScoreSource(decision: TradeDecision): string | null {
  if (pickNumber(decision.score_summary, "aggregated_score") !== null) return "score_summary.aggregated_score";
  if (pickNumber(decision.metadata, "score") !== null) return "metadata.score";
  if (pickNumber(decision.risk_summary, "score") !== null) return "risk_summary.score";
  return null;
}

export function getDecisionScore(decision: TradeDecision): number | null {
  const source = getDecisionScoreSource(decision);
  const value = source === "score_summary.aggregated_score"
    ? pickNumber(decision.score_summary, "aggregated_score")
    : source === "metadata.score"
      ? pickNumber(decision.metadata, "score")
      : source === "risk_summary.score"
        ? pickNumber(decision.risk_summary, "score")
        : null;

  logMetric("score", decision, source, value);
  return value;
}

export function getDecisionConfidenceSource(decision: TradeDecision): string | null {
  if (pickNumber(decision.score_summary, "confidence") !== null) return "score_summary.confidence";
  if (pickNumber(decision.metadata, "confidence") !== null) return "metadata.confidence";
  if (pickNumber(decision.risk_summary, "confidence") !== null) return "risk_summary.confidence";
  if (pickText(decision.score_summary, "confidence") !== null) return "score_summary.confidence";
  if (pickText(decision.metadata, "confidence") !== null) return "metadata.confidence";
  if (pickText(decision.risk_summary, "confidence") !== null) return "risk_summary.confidence";
  return null;
}

export function getDecisionConfidence(decision: TradeDecision): ConfidenceValue {
  const numeric =
    pickNumber(decision.score_summary, "confidence")
    ?? pickNumber(decision.metadata, "confidence")
    ?? pickNumber(decision.risk_summary, "confidence");

  if (numeric !== null) {
    logMetric("confidence", decision, getDecisionConfidenceSource(decision), numeric);
    return numeric;
  }

  const stringValue =
    pickText(decision.score_summary, "confidence")
    ?? pickText(decision.metadata, "confidence")
    ?? pickText(decision.risk_summary, "confidence");

  logMetric("confidence", decision, getDecisionConfidenceSource(decision), stringValue);
  return stringValue;
}

export function formatScoreCell(decision: TradeDecision): string {
  return formatPercentish(getDecisionScore(decision));
}

export function formatConfidenceCell(decision: TradeDecision): string {
  const value = getDecisionConfidence(decision);
  if (typeof value === "string") return value;
  return formatPercentish(value);
}

export function getDecisionReasoning(decision: TradeDecision): string | null {
  if (typeof decision.reasoning === "string" && decision.reasoning) return decision.reasoning;
  return pickText(decision.score_summary, "reasoning");
}

export function getDecisionRationale(decision: TradeDecision): string | null {
  if (typeof decision.rejection_reason === "string" && decision.rejection_reason) return decision.rejection_reason;
  if (typeof decision.approval_reason === "string" && decision.approval_reason) return decision.approval_reason;

  const reasoning = getDecisionReasoning(decision);
  if (reasoning) return reasoning;

  const veto = decision.veto_summary as Record<string, unknown> | null | undefined;
  if (!veto) return null;

  return text(veto.reason) ?? text(veto.veto_reason);
}
