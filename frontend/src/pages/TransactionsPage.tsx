import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { Account, CategoryGroup, Transaction } from "../api/types";
import { currentMonth } from "../lib/dates";
import { formatCents } from "../lib/money";
import { YnabTransactionImportModal, type ImportRow } from "./YnabTransactionImportModal";

function monthStart(month: string): string {
  return `${month}-01`;
}

function monthEnd(month: string): string {
  const [year, m] = month.split("-").map(Number);
  const lastDay = new Date(year, m, 0).getDate();
  return `${month}-${String(lastDay).padStart(2, "0")}`;
}

export function TransactionsPage() {
  const [startDate, setStartDate] = useState(() => monthStart(currentMonth()));
  const [endDate, setEndDate] = useState(() => monthEnd(currentMonth()));
  const [selectedAccountIds, setSelectedAccountIds] = useState(() => new Set<number>());
  const [selectedCategoryId, setSelectedCategoryId] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  const qc = useQueryClient();

  const importMutation = useMutation({
    mutationFn: (rows: ImportRow[]) =>
      api<{ imported: number }>("/api/transactions/import-ynab", { method: "POST", body: { rows } }),
    onSuccess: () => {
      setImportOpen(false);
      void qc.invalidateQueries({ queryKey: ["transactions"] });
      void qc.invalidateQueries({ queryKey: ["accounts"] });
    },
  });

  const txnsQuery = useQuery<Transaction[]>({
    queryKey: ["transactions", startDate, endDate],
    queryFn: () =>
      api<Transaction[]>(`/api/transactions?start_date=${startDate}&end_date=${endDate}`),
  });

  const accountsQuery = useQuery<Account[]>({
    queryKey: ["accounts"],
    queryFn: () => api<Account[]>("/api/accounts"),
  });

  const groupsQuery = useQuery<CategoryGroup[]>({
    queryKey: ["category-groups"],
    queryFn: () => api<CategoryGroup[]>("/api/category-groups"),
  });

  const accounts = accountsQuery.data ?? [];
  const flatCategories =
    groupsQuery.data?.flatMap((g) =>
      g.categories.map((c) => ({ ...c, groupName: g.name })),
    ) ?? [];

  function toggleAccount(id: number) {
    setSelectedAccountIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const filteredTxns = (txnsQuery.data ?? []).filter((t) => {
    if (selectedAccountIds.size > 0 && !selectedAccountIds.has(t.account_id)) return false;
    if (selectedCategoryId === "null") {
      if (t.category_id !== null) return false;
    } else if (selectedCategoryId !== "") {
      if (t.category_id !== Number(selectedCategoryId)) return false;
    }
    return true;
  });

  const accountById = Object.fromEntries(accounts.map((a) => [a.id, a]));
  const categoryById = Object.fromEntries(flatCategories.map((c) => [c.id, c]));

  return (
    <div className="max-w-5xl space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Transactions</h1>
        <button
          type="button"
          onClick={() => setImportOpen(true)}
          className="border border-stone-300 dark:border-stone-600 text-stone-700 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 rounded-lg px-4 py-2 text-sm"
        >
          Import YNAB
        </button>
      </div>

      {/* Filter panel */}
      <div className="bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 rounded-2xl p-5 space-y-4">
        <div className="flex flex-wrap gap-6 items-end">
          {/* Date range */}
          <div className="flex gap-3 items-end">
            <div className="space-y-1">
              <label className="text-sm font-medium text-stone-700 dark:text-stone-300">From</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="h-9 border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 text-sm"
              />
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium text-stone-700 dark:text-stone-300">To</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="h-9 border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 text-sm"
              />
            </div>
          </div>

          {/* Category */}
          <div className="space-y-1">
            <label className="text-sm font-medium text-stone-700 dark:text-stone-300">Category</label>
            <div className="relative">
              <select
                value={selectedCategoryId}
                onChange={(e) => setSelectedCategoryId(e.target.value)}
                className="h-9 w-full appearance-none border border-stone-300 dark:border-stone-600 rounded-lg pl-3 pr-8 text-sm bg-white dark:bg-stone-900"
              >
                <option value="">All categories</option>
                <option value="null">Unassigned</option>
                {flatCategories.map((c) => (
                  <option key={c.id} value={String(c.id)}>
                    {c.groupName} › {c.name}
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
        </div>

        {/* Account checkboxes */}
        {accounts.length > 0 && (
          <div className="space-y-1">
            <div className="text-sm font-medium text-stone-700 dark:text-stone-300">Accounts</div>
            <div className="flex flex-wrap gap-3">
              {accounts.map((a) => (
                <label
                  key={a.id}
                  className="flex items-center gap-1.5 text-sm text-stone-700 dark:text-stone-300 cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={selectedAccountIds.has(a.id)}
                    onChange={() => toggleAccount(a.id)}
                    className="rounded accent-indigo-600"
                  />
                  {a.name}
                </label>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Transaction table */}
      <div className="bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 rounded-2xl overflow-hidden">
        {txnsQuery.isLoading && (
          <div className="p-5 text-stone-500 dark:text-stone-400">Loading…</div>
        )}
        {!txnsQuery.isLoading && filteredTxns.length === 0 && (
          <div className="p-5 text-stone-500 dark:text-stone-400">No transactions found.</div>
        )}
        {filteredTxns.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs uppercase text-stone-500 dark:text-stone-400">
                <tr>
                  <th className="text-left px-5 py-2">Date</th>
                  <th className="text-left px-5 py-2">Account</th>
                  <th className="text-left px-5 py-2">Payee</th>
                  <th className="text-left px-5 py-2">Category</th>
                  <th className="hidden sm:table-cell text-left px-5 py-2">Memo</th>
                  <th className="text-right px-5 py-2">Amount</th>
                </tr>
              </thead>
              <tbody>
                {filteredTxns.map((t) => {
                  const account = accountById[t.account_id];
                  const cat = t.category_id !== null ? categoryById[t.category_id] : null;
                  return (
                    <tr key={t.id} className="border-t border-stone-100 dark:border-stone-800">
                      <td className="px-5 py-2 text-stone-600 dark:text-stone-400">{t.date}</td>
                      <td className="px-5 py-2 text-stone-600 dark:text-stone-400">
                        {account?.name ?? <span className="text-stone-400 dark:text-stone-500">—</span>}
                      </td>
                      <td className="px-5 py-2">
                        {t.payee || <span className="text-stone-400 dark:text-stone-500">—</span>}
                      </td>
                      <td className="px-5 py-2">
                        {cat ? (
                          `${cat.groupName} › ${cat.name}`
                        ) : (
                          <span className="text-stone-400 dark:text-stone-500">Unassigned</span>
                        )}
                      </td>
                      <td className="hidden sm:table-cell px-5 py-2 text-stone-500 dark:text-stone-400">
                        {t.memo}
                      </td>
                      <td
                        className={`px-5 py-2 text-right tabular-nums ${
                          t.amount_cents >= 0
                            ? "text-emerald-700 dark:text-emerald-400"
                            : "text-stone-900 dark:text-stone-100"
                        }`}
                      >
                        {formatCents(t.amount_cents)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {importOpen && (
        <YnabTransactionImportModal
          accounts={accounts}
          categoryGroups={groupsQuery.data ?? []}
          onImport={(rows) => importMutation.mutate(rows)}
          isPending={importMutation.isPending}
          onClose={() => setImportOpen(false)}
        />
      )}
    </div>
  );
}
