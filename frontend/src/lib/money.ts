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
 *
 * European-first: when both '.' and ',' appear, '.' is treated as the
 * thousands separator and ',' as the decimal (so "1.234,56" → 123456 cents).
 * A bare comma is also treated as a decimal separator. Currency symbols and
 * whitespace are stripped. Returns null for empty, non-numeric, or
 * symbol-only input.
 */
export function parseAmountToCents(raw: string): number | null {
  if (!raw) return null;
  let s = raw.replace(/[€$\s]/g, "");
  // Reject input that has no digits at all — guards against "€€€" and the
  // like, where Number("") silently returns 0.
  if (!/\d/.test(s)) return null;
  if (s.includes(",") && s.includes(".")) {
    s = s.replace(/\./g, "").replace(",", ".");
  } else if (s.includes(",")) {
    s = s.replace(",", ".");
  }
  const num = Number(s);
  if (!Number.isFinite(num)) return null;
  return Math.round(num * 100);
}
