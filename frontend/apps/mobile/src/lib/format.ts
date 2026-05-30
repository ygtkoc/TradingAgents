export function label(value?: string | null) {
  return (value ?? "unknown").replaceAll("_", " ").toUpperCase();
}

export function minutesAgo(value?: string | null) {
  if (!value) {
    return "now";
  }

  const diff = Math.max(1, Math.round((Date.now() - new Date(value).getTime()) / 60000));

  if (diff < 60) {
    return `${diff}m`;
  }

  return `${Math.round(diff / 60)}h`;
}

export function percent(value?: number | null) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "0.00%";
  }

  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

export function rMultiple(value?: number | string | null) {
  const numeric = Number(value);

  if (!Number.isFinite(numeric)) {
    return "0.0R";
  }

  return `${numeric > 0 ? "+" : ""}${numeric.toFixed(1)}R`;
}

export function scoreFromSummary(summary?: Record<string, unknown> | null) {
  const value = summary?.aggregated_score ?? summary?.score;
  const numeric = Number(value);

  return Number.isFinite(numeric) ? Math.round(numeric) : null;
}
