import { useRef, useState } from "react";
import type { Account, CategoryGroup } from "../api/types";
import { formatCents } from "../lib/money";

type ParsedRow = {
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

function parseCsvLine(line: string): string[] {
  const fields: string[] = [];
  let i = 0;
  while (i <= line.length) {
    if (line[i] === '"') {
      i++;
      let field = "";
      while (i < line.length) {
        if (line[i] === '"' && line[i + 1] === '"') {
          field += '"';
          i += 2;
        } else if (line[i] === '"') {
          i++;
          break;
        } else {
          field += line[i++];
        }
      }
      fields.push(field);
      if (line[i] === ",") i++;
    } else {
      let field = "";
      while (i < line.length && line[i] !== ",") field += line[i++];
      fields.push(field.trim());
      if (line[i] === ",") i++;
    }
  }
  return fields;
}

function parseCurrencyToCents(raw: string): number {
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

function parseYnabDate(raw: string): string {
  // "28/07/2026" → "2026-07-28"
  const parts = raw.split("/");
  if (parts.length !== 3) return raw;
  const [day, month, year] = parts;
  return `${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}`;
}

function parseYnabTransactionCsv(text: string): ParsedRow[] {
  const lines = text.split(/\r?\n/);
  const rows: ParsedRow[] = [];
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

function resolveCategoryId(
  categoryGroup: string,
  category: string,
  accountScope: string,
  categoryGroups: CategoryGroup[],
): number | null {
  if (!categoryGroup || !category) return null;
  const group = categoryGroups.find((g) => g.name === categoryGroup);
  if (!group || group.scope !== accountScope) return null;
  const cat = group.categories.find((c) => c.name === category);
  return cat?.id ?? null;
}

const SKIP_VALUE = "__skip__";

export function YnabTransactionImportModal({
  accounts,
  categoryGroups,
  onImport,
  isPending,
  onClose,
}: {
  accounts: Account[];
  categoryGroups: CategoryGroup[];
  onImport: (rows: ImportRow[]) => void;
  isPending: boolean;
  onClose: () => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [parsedRows, setParsedRows] = useState<ParsedRow[] | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  // Maps csvAccountName → account_id (string) or SKIP_VALUE
  const [mappings, setMappings] = useState<Record<string, string>>({});
  const [step, setStep] = useState<1 | 2>(1);

  function handleFile(file: File) {
    setFileError(null);
    setParsedRows(null);
    setMappings({});
    setStep(1);
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      const rows = parseYnabTransactionCsv(text);
      if (rows.length === 0) {
        setFileError("No valid rows found. Make sure this is a YNAB transactions CSV.");
        return;
      }
      const uniqueAccounts = Array.from(new Set(rows.map((r) => r.csvAccount)));
      const initialMappings: Record<string, string> = {};
      for (const name of uniqueAccounts) {
        const match = accounts.find(
          (a) => a.name.toLowerCase() === name.toLowerCase()
        );
        initialMappings[name] = match ? String(match.id) : "";
      }
      setMappings(initialMappings);
      setParsedRows(rows);
    };
    reader.readAsText(file);
  }

  const uniqueCsvAccounts = parsedRows
    ? Array.from(new Set(parsedRows.map((r) => r.csvAccount)))
    : [];

  const hasMappedAccount = Object.values(mappings).some(
    (v) => v !== "" && v !== SKIP_VALUE
  );

  function buildImportRows(): ImportRow[] {
    if (!parsedRows) return [];
    const rows: ImportRow[] = [];
    for (const row of parsedRows) {
      const mapping = mappings[row.csvAccount];
      if (!mapping || mapping === SKIP_VALUE || mapping === "") continue;
      const accountId = Number(mapping);
      const account = accounts.find((a) => a.id === accountId);
      if (!account) continue;
      const category_id = resolveCategoryId(
        row.categoryGroup,
        row.category,
        account.scope,
        categoryGroups,
      );
      rows.push({
        account_id: accountId,
        category_id,
        date: row.date,
        payee: row.payee,
        memo: row.memo,
        amount_cents: row.amount_cents,
      });
    }
    return rows;
  }

  const previewRows = step === 2 ? buildImportRows() : [];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-white dark:bg-stone-900 rounded-2xl shadow-xl w-full max-w-2xl max-h-[85vh] flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-stone-200 dark:border-stone-700">
          <h2 className="text-lg font-semibold">Import transactions from YNAB</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-stone-500 hover:text-stone-800 dark:hover:text-stone-200 text-xl leading-none"
          >
            ✕
          </button>
        </div>

        <div className="p-6 overflow-y-auto flex-1 space-y-5">
          {step === 1 && (
            <>
              <p className="text-sm text-stone-600 dark:text-stone-400">
                Export transactions from YNAB via{" "}
                <em>All Accounts → Export → Export to CSV</em>, then upload the file here.
              </p>

              <div>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".csv,text/csv"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleFile(file);
                  }}
                />
                <button
                  type="button"
                  onClick={() => fileRef.current?.click()}
                  className="border border-dashed border-stone-400 dark:border-stone-600 rounded-xl px-4 py-3 text-sm text-stone-600 dark:text-stone-400 hover:border-indigo-500 hover:text-indigo-600 dark:hover:text-indigo-400 w-full text-center transition-colors"
                >
                  {parsedRows ? "Choose a different file" : "Choose CSV file…"}
                </button>
                {fileError && (
                  <p className="mt-2 text-sm text-red-600 dark:text-red-400">{fileError}</p>
                )}
              </div>

              {parsedRows && (
                <div className="space-y-3">
                  <p className="text-sm font-medium text-stone-700 dark:text-stone-300">
                    Map accounts
                    <span className="ml-2 font-normal text-stone-500 dark:text-stone-400">
                      {parsedRows.length} transaction{parsedRows.length !== 1 ? "s" : ""} found
                    </span>
                  </p>
                  <div className="border border-stone-200 dark:border-stone-700 rounded-xl overflow-hidden divide-y divide-stone-100 dark:divide-stone-800">
                    {uniqueCsvAccounts.map((csvName) => (
                      <div
                        key={csvName}
                        className="px-4 py-3 flex items-center justify-between gap-4"
                      >
                        <span className="text-sm text-stone-700 dark:text-stone-200 truncate">
                          {csvName}
                        </span>
                        <div className="relative shrink-0">
                          <select
                            value={mappings[csvName] ?? ""}
                            onChange={(e) =>
                              setMappings((prev) => ({ ...prev, [csvName]: e.target.value }))
                            }
                            className="h-9 appearance-none border border-stone-300 dark:border-stone-600 rounded-lg pl-3 pr-8 text-sm bg-white dark:bg-stone-900"
                          >
                            <option value="">— select account —</option>
                            <option value={SKIP_VALUE}>Skip</option>
                            {accounts.map((a) => (
                              <option key={a.id} value={String(a.id)}>
                                {a.name}
                              </option>
                            ))}
                          </select>
                          <div className="pointer-events-none absolute inset-y-0 right-2 flex items-center text-stone-400 dark:text-stone-500">
                            <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                              <path d="M4 6l4 4 4-4" />
                            </svg>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}

          {step === 2 && (
            <div className="space-y-3">
              <p className="text-sm font-medium text-stone-700 dark:text-stone-300">
                Preview
                <span className="ml-2 font-normal text-stone-500 dark:text-stone-400">
                  {previewRows.length} transaction{previewRows.length !== 1 ? "s" : ""} to import
                </span>
              </p>
              <div className="border border-stone-200 dark:border-stone-700 rounded-xl overflow-hidden">
                <div className="overflow-x-auto max-h-80">
                  <table className="w-full text-sm">
                    <thead className="text-xs uppercase text-stone-500 dark:text-stone-400 bg-stone-50 dark:bg-stone-800">
                      <tr>
                        <th className="text-left px-4 py-2">Date</th>
                        <th className="text-left px-4 py-2">Payee</th>
                        <th className="text-left px-4 py-2">Account</th>
                        <th className="text-right px-4 py-2">Amount</th>
                      </tr>
                    </thead>
                    <tbody>
                      {previewRows.map((row, i) => {
                        const account = accounts.find((a) => a.id === row.account_id);
                        return (
                          <tr
                            key={i}
                            className="border-t border-stone-100 dark:border-stone-800"
                          >
                            <td className="px-4 py-1.5 text-stone-600 dark:text-stone-400">
                              {row.date}
                            </td>
                            <td className="px-4 py-1.5 truncate max-w-[160px]">
                              {row.payee || (
                                <span className="text-stone-400 dark:text-stone-500">—</span>
                              )}
                            </td>
                            <td className="px-4 py-1.5 text-stone-600 dark:text-stone-400">
                              {account?.name}
                            </td>
                            <td
                              className={`px-4 py-1.5 text-right tabular-nums ${
                                row.amount_cents >= 0
                                  ? "text-emerald-700 dark:text-emerald-400"
                                  : "text-stone-900 dark:text-stone-100"
                              }`}
                            >
                              {formatCents(row.amount_cents)}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="flex justify-between gap-3 px-6 py-4 border-t border-stone-200 dark:border-stone-700">
          <div>
            {step === 2 && (
              <button
                type="button"
                onClick={() => setStep(1)}
                disabled={isPending}
                className="text-sm text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-200 disabled:opacity-50"
              >
                ← Back
              </button>
            )}
          </div>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={onClose}
              disabled={isPending}
              className="border border-stone-300 dark:border-stone-600 text-stone-700 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 rounded-lg px-4 py-2 text-sm disabled:opacity-50"
            >
              Cancel
            </button>
            {step === 1 && (
              <button
                type="button"
                onClick={() => setStep(2)}
                disabled={!parsedRows || !hasMappedAccount}
                className="bg-indigo-600 hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg px-4 py-2 text-sm font-medium"
              >
                Continue
              </button>
            )}
            {step === 2 && (
              <button
                type="button"
                onClick={() => onImport(previewRows)}
                disabled={previewRows.length === 0 || isPending}
                className="bg-indigo-600 hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg px-4 py-2 text-sm font-medium"
              >
                {isPending
                  ? "Importing…"
                  : `Import ${previewRows.length} transaction${previewRows.length !== 1 ? "s" : ""}`}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
