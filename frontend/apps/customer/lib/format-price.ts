export function formatPrice(value: number, currency = "USD", locale = "en-US"): string {
  const fractionDigits = priceFractionDigits(value);
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    minimumFractionDigits: Math.min(2, fractionDigits),
    maximumFractionDigits: fractionDigits,
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
