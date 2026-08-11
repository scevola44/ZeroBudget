import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type {
  Account,
  CategoryGroup,
  Payee,
  Transaction,
  TransactionListResponse,
} from "../api/types";
import {
  EditTransactionModal,
  type TransactionEdit,
} from "../components/EditTransactionModal";
import { PayeeManager } from "../components/PayeeManager";
import { TransferSuggestionsBanner } from "../components/TransferSuggestionsBanner";
import { currentMonth } from "../lib/dates";
import { formatCents } from "../lib/money";
import { useDebouncedValue } from "../lib/useDebouncedValue";
import { YnabTransactionImportModal, type ImportRow } from "./YnabTransactionImportModal";

const PAGE_SIZE = 100;
// A sentinel client-side value for the "Unassigned" filter option — translated
// to the `uncategorized` boolean query param before it ever reaches the API,
// so the backend never sees a magic string in category_id's place.
const UNASSIGNED_SENTINEL = "unassigned";

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
  const [searchText, setSearchText] = useState("");
  const [offset, setOffset] = useState(0);
  const [selectedIds, setSelectedIds] = useState(() => new Set<number>());
  const [bulkCategoryChoice, setBulkCategoryChoice] = useState("");
  const [bulkError, setBulkError] = useState<string | null>(null);
  const [confirmingBulkDelete, setConfirmingBulkDelete] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [editingTxnId, setEditingTxnId] = useState<number | null>(null);
  const [editError, setEditError] = useState<string | null>(null);
  const qc = useQueryClient();

  const debouncedSearch = useDebouncedValue(searchText, 300);

  const queryParams = useMemo(() => {
    const params = new URLSearchParams();
    params.set("start_date", startDate);
    params.set("end_date", endDate);
    for (const id of selectedAccountIds) params.append("account_id", String(id));
    if (selectedCategoryId === UNASSIGNED_SENTINEL) {
      params.set("uncategorized", "true");
    } else if (selectedCategoryId !== "") {
      params.set("category_id", selectedCategoryId);
    }
    if (debouncedSearch.trim()) params.set("q", debouncedSearch.trim());
    params.set("limit", String(PAGE_SIZE));
    params.set("offset", String(offset));
    return params.toString();
  }, [startDate, endDate, selectedAccountIds, selectedCategoryId, debouncedSearch, offset]);

  // A bulk action must never silently apply to rows the user can no longer
  // see once filters, search, or the page change underneath it.
  useEffect(() => {
    setSelectedIds(new Set());
  }, [queryParams]);

  function resetToFirstPage() {
    setOffset(0);
  }

  const importMutation = useMutation({
    mutationFn: (rows: ImportRow[]) =>
      api<{ imported: number }>("/api/transactions/import-ynab", { method: "POST", body: { rows } }),
    onSuccess: () => {
      setImportOpen(false);
      void qc.invalidateQueries({ queryKey: ["transactions"] });
      void qc.invalidateQueries({ queryKey: ["accounts"] });
      void qc.invalidateQueries({ queryKey: ["payees"] });
    },
  });

  const txnsQuery = useQuery<TransactionListResponse>({
    queryKey: ["transactions", queryParams],
    queryFn: () => api<TransactionListResponse>(`/api/transactions?${queryParams}`),
  });
  const txns = txnsQuery.data?.items ?? [];
  const total = txnsQuery.data?.total ?? 0;

  const accountsQuery = useQuery<Account[]>({
    queryKey: ["accounts"],
    queryFn: () => api<Account[]>("/api/accounts"),
  });

  const groupsQuery = useQuery<CategoryGroup[]>({
    queryKey: ["category-groups"],
    queryFn: () => api<CategoryGroup[]>("/api/category-groups"),
  });

  const payeesQuery = useQuery<Payee[]>({
    queryKey: ["payees"],
    queryFn: () => api<Payee[]>("/api/payees"),
  });

  const accounts = accountsQuery.data ?? [];
  const flatCategories =
    groupsQuery.data?.flatMap((g) =>
      g.categories.map((c) => ({ ...c, groupName: g.name, groupScope: g.scope })),
    ) ?? [];

  // A transfer touches two accounts, so the broad prefix has to go too.
  function invalidateAfterChange() {
    void qc.invalidateQueries({ queryKey: ["transactions"] });
    void qc.invalidateQueries({ queryKey: ["accounts"] });
    void qc.invalidateQueries({ queryKey: ["budget"] });
    void qc.invalidateQueries({ queryKey: ["payees"] });
  }

  const updateTxn = useMutation({
    mutationFn: ({ txnId, edit }: { txnId: number; edit: TransactionEdit }) =>
      api<Transaction>(`/api/transactions/${txnId}`, { method: "PATCH", body: edit }),
    onSuccess: () => {
      setEditingTxnId(null);
      setEditError(null);
      invalidateAfterChange();
    },
    onError: (err) => setEditError(err instanceof Error ? err.message : "Update failed"),
  });

  const unlinkTransfer = useMutation({
    mutationFn: (txnId: number) =>
      api(`/api/transactions/${txnId}/transfer-link`, { method: "DELETE" }),
    onSuccess: () => {
      setEditingTxnId(null);
      setEditError(null);
      invalidateAfterChange();
      void qc.invalidateQueries({ queryKey: ["transfer-suggestions"] });
    },
    onError: (err) =>
      setEditError(err instanceof Error ? err.message : "Could not unlink the transfer"),
  });

  const bulkSetCategory = useMutation({
    mutationFn: (categoryId: number | null) =>
      api<{ updated: number }>("/api/transactions/bulk-category", {
        method: "PATCH",
        body: { transaction_ids: Array.from(selectedIds), category_id: categoryId },
      }),
    onSuccess: () => {
      setSelectedIds(new Set());
      setBulkCategoryChoice("");
      setBulkError(null);
      invalidateAfterChange();
    },
    onError: (err) =>
      setBulkError(err instanceof Error ? err.message : "Could not set the category"),
  });

  const bulkDelete = useMutation({
    mutationFn: () =>
      api<{ deleted: number }>("/api/transactions/bulk-delete", {
        method: "POST",
        body: { transaction_ids: Array.from(selectedIds) },
      }),
    onSuccess: () => {
      setSelectedIds(new Set());
      setConfirmingBulkDelete(false);
      setBulkError(null);
      invalidateAfterChange();
    },
    onError: (err) => setBulkError(err instanceof Error ? err.message : "Could not delete"),
  });

  function toggleAccount(id: number) {
    setSelectedAccountIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    resetToFirstPage();
  }

  function toggleSelected(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAllVisible() {
    setSelectedIds((prev) =>
      txns.every((t) => prev.has(t.id)) ? new Set() : new Set(txns.map((t) => t.id)),
    );
  }

  const accountById = Object.fromEntries(accounts.map((a) => [a.id, a]));
  const categoryById = Object.fromEntries(flatCategories.map((c) => [c.id, c]));
  const editingTransaction =
    editingTxnId === null ? undefined : txns.find((t) => t.id === editingTxnId);

  const allVisibleSelected = txns.length > 0 && txns.every((t) => selectedIds.has(t.id));
  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = Math.min(offset + PAGE_SIZE, total);

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

      {/* Renders nothing when there is nothing to suggest, so it can't leave a
          gap in the page's vertical rhythm. */}
      <TransferSuggestionsBanner
        startDate={startDate}
        endDate={endDate}
        accountById={accountById}
        onLinked={invalidateAfterChange}
      />

      {/* Renders nothing until at least one payee exists. */}
      <PayeeManager payees={payeesQuery.data ?? []} />

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
                onChange={(e) => {
                  setStartDate(e.target.value);
                  resetToFirstPage();
                }}
                className="h-9 border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 text-sm"
              />
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium text-stone-700 dark:text-stone-300">To</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => {
                  setEndDate(e.target.value);
                  resetToFirstPage();
                }}
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
                onChange={(e) => {
                  setSelectedCategoryId(e.target.value);
                  resetToFirstPage();
                }}
                className="h-9 w-full appearance-none border border-stone-300 dark:border-stone-600 rounded-lg pl-3 pr-8 text-sm bg-white dark:bg-stone-900"
              >
                <option value="">All categories</option>
                <option value={UNASSIGNED_SENTINEL}>Unassigned</option>
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

          {/* Search */}
          <div className="space-y-1 flex-1 min-w-[12rem]">
            <label className="text-sm font-medium text-stone-700 dark:text-stone-300">Search</label>
            <input
              value={searchText}
              onChange={(e) => {
                setSearchText(e.target.value);
                resetToFirstPage();
              }}
              placeholder="Payee or memo"
              className="h-9 w-full border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 text-sm"
            />
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

      {/* Bulk action bar */}
      {selectedIds.size > 0 && (
        <div className="bg-indigo-50 dark:bg-indigo-950/40 border border-indigo-200 dark:border-indigo-800 rounded-2xl px-5 py-3 flex flex-wrap items-center gap-3">
          <span className="text-sm font-medium text-indigo-900 dark:text-indigo-200">
            {selectedIds.size} selected
          </span>
          <div className="relative">
            <select
              value={bulkCategoryChoice}
              onChange={(e) => {
                const value = e.target.value;
                setBulkCategoryChoice(value);
                if (value === "") return;
                setBulkError(null);
                bulkSetCategory.mutate(value === UNASSIGNED_SENTINEL ? null : Number(value));
              }}
              disabled={bulkSetCategory.isPending}
              className="h-9 appearance-none border border-stone-300 dark:border-stone-600 rounded-lg pl-3 pr-8 text-sm bg-white dark:bg-stone-900 disabled:opacity-50"
            >
              <option value="">Set category…</option>
              <option value={UNASSIGNED_SENTINEL}>Unassigned</option>
              {flatCategories.map((c) => (
                <option key={c.id} value={String(c.id)}>
                  {c.groupName} › {c.name}
                </option>
              ))}
            </select>
          </div>
          {confirmingBulkDelete ? (
            <button
              type="button"
              onClick={() => bulkDelete.mutate()}
              disabled={bulkDelete.isPending}
              className="text-sm bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white rounded-lg px-3 py-2"
            >
              Confirm delete {selectedIds.size}?
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmingBulkDelete(true)}
              className="text-sm text-red-600 dark:text-red-400 hover:underline"
            >
              Delete
            </button>
          )}
          <button
            type="button"
            onClick={() => {
              setSelectedIds(new Set());
              setConfirmingBulkDelete(false);
            }}
            className="text-sm text-stone-500 dark:text-stone-400 hover:underline"
          >
            Clear selection
          </button>
          {bulkError && <span className="text-sm text-red-600 dark:text-red-400">{bulkError}</span>}
        </div>
      )}

      {/* Transaction table */}
      <div className="bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 rounded-2xl overflow-hidden">
        {txnsQuery.isLoading && (
          <div className="p-5 text-stone-500 dark:text-stone-400">Loading…</div>
        )}
        {!txnsQuery.isLoading && txns.length === 0 && (
          <div className="p-5 text-stone-500 dark:text-stone-400">No transactions found.</div>
        )}
        {txns.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs uppercase text-stone-500 dark:text-stone-400">
                <tr>
                  <th className="px-5 py-2 w-8">
                    <input
                      type="checkbox"
                      checked={allVisibleSelected}
                      onChange={toggleSelectAllVisible}
                      className="rounded accent-indigo-600"
                    />
                  </th>
                  <th className="text-left px-5 py-2">Date</th>
                  <th className="text-left px-5 py-2">Account</th>
                  <th className="text-left px-5 py-2">Payee</th>
                  <th className="text-left px-5 py-2">Category</th>
                  <th className="hidden sm:table-cell text-left px-5 py-2">Memo</th>
                  <th className="text-right px-5 py-2">Amount</th>
                  <th className="px-5 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {txns.map((t) => {
                  const account = accountById[t.account_id];
                  const cat = t.category_id !== null ? categoryById[t.category_id] : null;
                  return (
                    <tr key={t.id} className="border-t border-stone-100 dark:border-stone-800">
                      <td className="px-5 py-2">
                        <input
                          type="checkbox"
                          checked={selectedIds.has(t.id)}
                          onChange={() => toggleSelected(t.id)}
                          className="rounded accent-indigo-600"
                        />
                      </td>
                      <td className="px-5 py-2 text-stone-600 dark:text-stone-400">{t.date}</td>
                      <td className="px-5 py-2 text-stone-600 dark:text-stone-400">
                        {account?.name ?? <span className="text-stone-400 dark:text-stone-500">—</span>}
                      </td>
                      <td className="px-5 py-2">
                        {t.payee || <span className="text-stone-400 dark:text-stone-500">—</span>}
                      </td>
                      <td className="px-5 py-2">
                        {t.transfer_peer_id !== null ? (
                          <span className="text-stone-600 dark:text-stone-300">
                            Transfer :{" "}
                            {(t.transfer_peer_account_id !== null
                              ? accountById[t.transfer_peer_account_id]?.name
                              : undefined) ?? "another account"}
                          </span>
                        ) : t.splits.length > 0 ? (
                          `Split (${t.splits.length})`
                        ) : cat ? (
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
                      <td className="px-5 py-2 text-right">
                        <button
                          onClick={() => {
                            setEditError(null);
                            setEditingTxnId(t.id);
                          }}
                          className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline px-2 py-1"
                        >
                          Edit
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {total > 0 && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-stone-100 dark:border-stone-800 text-sm text-stone-500 dark:text-stone-400">
            <span>
              Showing {pageStart}–{pageEnd} of {total}
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
                disabled={offset === 0}
                className="border border-stone-300 dark:border-stone-600 rounded-lg px-3 py-1.5 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-stone-100 dark:hover:bg-stone-800"
              >
                Prev
              </button>
              <button
                type="button"
                onClick={() => setOffset((o) => o + PAGE_SIZE)}
                disabled={offset + PAGE_SIZE >= total}
                className="border border-stone-300 dark:border-stone-600 rounded-lg px-3 py-1.5 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-stone-100 dark:hover:bg-stone-800"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {editingTransaction && (
        <EditTransactionModal
          transaction={editingTransaction}
          // Only categories in the transaction's own scope are valid — the
          // backend rejects the rest with a 422.
          categories={flatCategories.filter(
            (c) => c.groupScope === accountById[editingTransaction.account_id]?.scope,
          )}
          peerAccount={
            (editingTransaction.transfer_peer_account_id !== null
              ? accountById[editingTransaction.transfer_peer_account_id]
              : undefined) ?? null
          }
          isOpen={true}
          onClose={() => {
            setEditingTxnId(null);
            setEditError(null);
          }}
          onSave={(edit) => updateTxn.mutate({ txnId: editingTransaction.id, edit })}
          onUnlinkTransfer={() => unlinkTransfer.mutate(editingTransaction.id)}
          isPending={updateTxn.isPending || unlinkTransfer.isPending}
          error={editError}
        />
      )}

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
