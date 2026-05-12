/**
 * Display-only formatters. Do NOT use these results for arithmetic — they
 * are strings.
 */

export function formatCurrency(value: number, currency = "USD", locale = "en-US"): string {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatPercent(value: number, fractionDigits = 2, locale = "en-US"): string {
  return new Intl.NumberFormat(locale, {
    style: "percent",
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value / 100);
}

export function formatNumber(value: number, fractionDigits = 4, locale = "en-US"): string {
  return new Intl.NumberFormat(locale, {
    maximumFractionDigits: fractionDigits,
  }).format(value);
}

export function shortId(id: string, len = 6): string {
  if (id.length <= len * 2) return id;
  return `${id.slice(0, len)}…${id.slice(-len)}`;
}
