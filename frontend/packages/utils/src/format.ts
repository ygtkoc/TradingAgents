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

function priceFractionDigits(value: number): number {
  const abs = Math.abs(value);
  if (abs === 0) return 2;
  if (abs >= 1000) return 2;
  if (abs >= 100) return 3;
  if (abs >= 0.1) return 4;
  if (abs >= 0.01) return 6;
  return 8;
}

export function formatPrice(value: number, currency = "USD", locale = "en-US"): string {
  const fractionDigits = priceFractionDigits(value);
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    minimumFractionDigits: Math.min(2, fractionDigits),
    maximumFractionDigits: fractionDigits,
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
