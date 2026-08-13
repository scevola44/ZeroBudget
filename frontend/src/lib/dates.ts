// Month helpers keep every component on the same page about what "month"
// means: a string "YYYY-MM" corresponding to the first day of that month.

export function currentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}${pad(now.getMonth() + 1)}`
    .replace(/^(\d{4})(\d{2})$/, "$1-$2");
}

export function shiftMonth(month: string, delta: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`;
}

export function monthLabel(month: string): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y, m - 1, 1);
  return d.toLocaleString("en-GB", { month: "long", year: "numeric" });
}

export function todayISO(): string {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

// "2026-08-12" -> "August 12, 2026", for grouping a transaction list by day.
export function formatDateHeading(iso: string): string {
  const [y, m, day] = iso.split("-").map(Number);
  const d = new Date(y, m - 1, day);
  return d.toLocaleDateString("en-GB", { month: "long", day: "numeric", year: "numeric" });
}

function pad(n: number): string {
  return String(n).padStart(2, "0");
}
