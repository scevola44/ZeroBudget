// All money in this app is stored as signed integer cents in EUR.
// These helpers translate between that representation and what a human types
// or sees on screen.

const eurFormatter = new Intl.NumberFormat("en-IE", {
  style: "currency",
  currency: "EUR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatCents(cents: number): string {
  return eurFormatter.format(cents / 100);
}

/**
 * Parse a user-entered amount string into signed integer cents.
 * Accepts: "1234.56", "1,234.56", "-42", "42,50" (comma decimal), "€123.45".
 * Returns null if the value can't be interpreted as a number.
 */
export function parseAmountToCents(raw: string): number | null {
  if (!raw) return null;
  // Strip currency symbols and whitespace, normalize comma decimals.
  let s = raw.replace(/[€$\s]/g, "");
  // If the string has both '.' and ',' assume '.' is thousand sep (European).
  if (s.includes(",") && s.includes(".")) {
    s = s.replace(/\./g, "").replace(",", ".");
  } else if (s.includes(",") && !s.includes(".")) {
    s = s.replace(",", ".");
  }
  const num = Number(s);
  if (!Number.isFinite(num)) return null;
  return Math.round(num * 100);
}
