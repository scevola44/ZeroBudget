import type { CategoryGroup } from "../api/types";
import { parseCsvLine } from "./csv";

export type ParsedTransactionRow = {
  csvAccount: string;
  date: string; // YYYY-MM-DD
  payee: string;
  categoryGroup: string;
  category: string;
  memo: string;
  amount_cents: number;
};

export type ImportRow = {
  account_id: number;
  category_id: number | null;
  date: string;
  payee: string;
  memo: string;
  amount_cents: number;
};

export function parseCurrencyToCents(raw: string): number {
  const stripped = raw.replace(/[^0-9.,]/g, "");
  if (!stripped) return 0;
  let normalized: string;
  if (stripped.includes(".") && stripped.includes(",")) {
    // "1.234,56" → European format: "." is thousands separator
    normalized = stripped.replace(/\./g, "").replace(",", ".");
  } else {
    normalized = stripped.replace(",", ".");
  }
  const value = parseFloat(normalized);
  return isNaN(value) ? 0 : Math.round(value * 100);
}

export function parseYnabDate(raw: string): string {
  // "28/07/2026" → "2026-07-28"
  const parts = raw.split("/");
  if (parts.length !== 3) return raw;
  const [day, month, year] = parts;
  return `${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}`;
}

export function parseYnabTransactionCsv(text: string): ParsedTransactionRow[] {
  const lines = text.split(/\r?\n/);
  const rows: ParsedTransactionRow[] = [];
  for (const line of lines.slice(1)) {
    if (!line.trim()) continue;
    const cols = parseCsvLine(line);
    // Columns: Account[0], Flag[1], Date[2], Payee[3], CatGroupCat[4], CategoryGroup[5], Category[6], Memo[7], Outflow[8], Inflow[9], Cleared[10]
    const csvAccount = (cols[0] ?? "").trim();
    const date = parseYnabDate((cols[2] ?? "").trim());
    const payee = (cols[3] ?? "").trim().slice(0, 255);
    const categoryGroup = (cols[5] ?? "").trim();
    const category = (cols[6] ?? "").trim();
    const memo = (cols[7] ?? "").trim().slice(0, 500);
    const outflow = parseCurrencyToCents(cols[8] ?? "");
    const inflow = parseCurrencyToCents(cols[9] ?? "");
    const amount_cents = inflow - outflow;

    if (!csvAccount || !date) continue;
    rows.push({ csvAccount, date, payee, categoryGroup, category, memo, amount_cents });
  }
  return rows;
}

export function resolveCategoryId(
  categoryGroup: string,
  category: string,
  accountScopeId: number,
  categoryGroups: CategoryGroup[],
): number | null {
  if (!categoryGroup || !category) return null;
  const group = categoryGroups.find((g) => g.name === categoryGroup);
  if (!group || group.scope_id !== accountScopeId) return null;
  const cat = group.categories.find((c) => c.name === category);
  return cat?.id ?? null;
}
