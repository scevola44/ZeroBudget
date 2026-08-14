import { useEffect, useMemo, useRef, useState } from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import type { Account, BudgetMonth, CategoryGroup, Transaction, TransactionPage } from "../api/types";
import {
  AddTransactionModal,
  type TransactionCreateInput,
} from "../components/AddTransactionModal";
import { BulkDeleteTransactionsConfirmModal } from "../components/BulkDeleteTransactionsConfirmModal";
import { BulkSetCategoryModal } from "../components/BulkSetCategoryModal";
import { CategoryBadge, needsCategory } from "../components/CategoryBadge";
import type { CategoryBudgetInfo } from "../components/CategoryPicker";
import {
  EditTransactionModal,
  type TransactionEdit,
} from "../components/EditTransactionModal";
import { LinkTransferModal } from "../components/LinkTransferModal";
import { MobileTransactionRow } from "../components/MobileTransactionRow";
import { TransferSuggestionsBanner } from "../components/TransferSuggestionsBanner";
import { UnassignedTransactionsIsland } from "../components/UnassignedTransactionsIsland";
import { currentMonth, formatDateHeading } from "../lib/dates";
import { formatCents } from "../lib/money";
import { useDebouncedValue } from "../lib/useDebouncedValue";
import { YnabTransactionImportModal, type ImportRow } from "./YnabTransactionImportModal";

const PAGE_SIZE = 100;

function monthStart(month: string): string {
  return `${month}-01`;
}

function monthEnd(month: string): string {
  const [year, m] = month.split("-").map(Number);
  const lastDay = new Date(year, m, 0).getDate();
  return `${month}-${String(lastDay).padStart(2, "0")}`;
}

function fetchTransactionsPage(params: {
  startDate: string;
  endDate: string;
  accountIds: number[];
  categoryId: string;
  q: string;
  cursor?: string;
}): Promise<TransactionPage> {
  const search = new URLSearchParams();
  // Blank means open-ended, not "filter to nothing" — omit rather than send
  // an empty value FastAPI would fail to parse as a date.
  if (params.startDate) search.set("start_date", params.startDate);
  if (params.endDate) search.set("end_date", params.endDate);
  for (const id of params.accountIds) search.append("account_id", String(id));
  if (params.categoryId === "null") search.set("unassigned", "true");
  else if (params.categoryId === "rta") search.set("ready_to_assign", "true");
  else if (params.categoryId !== "") search.set("category_id", params.categoryId);
  if (params.q.trim()) search.set("q", params.q.trim());
  search.set("limit", String(PAGE_SIZE));
  if (params.cursor) search.set("cursor", params.cursor);
  return api<TransactionPage>(`/api/transactions?${search.toString()}`);
}

export function TransactionsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [startDate, setStartDate] = useState(() => monthStart(currentMonth()));
  const [endDate, setEndDate] = useState(() => monthEnd(currentMonth()));
  const [selectedAccountIds, setSelectedAccountIds] = useState(() => new Set<number>());
  const [selectedCategoryId, setSelectedCategoryId] = useState("null");
  const [searchInput, setSearchInput] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  const [editingTxnId, setEditingTxnId] = useState<number | null>(null);
  const [editError, setEditError] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(() => new Set());
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const [bulkDeleteError, setBulkDeleteError] = useState<string | null>(null);
  const [bulkSetCategoryOpen, setBulkSetCategoryOpen] = useState(false);
  const [bulkSetCategoryError, setBulkSetCategoryError] = useState<string | null>(null);
  const [selectionMode, setSelectionMode] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  // The existing row being linked to a transfer, and the account holding its
  // other leg — set together when "Transfer : <account>" is picked in the
  // edit modal.
  const [linking, setLinking] = useState<{ txnId: number; accountId: number } | null>(
    null,
  );
  const qc = useQueryClient();
  const debouncedSearch = useDebouncedValue(searchInput, 300);

  // Arriving from the unassigned-transactions island's "Review" link. A
  // plain lazy useState initializer wouldn't catch this when the click
  // happens from this same page (React Router updates the URL without
  // remounting), so this reacts to the search param instead. That count is
  // all-time, so the date range is cleared to open-ended too, or a row from
  // a past month would be filtered right back out. The param is stripped
  // once applied so it doesn't re-fight the user's own filter changes.
  useEffect(() => {
    if (searchParams.get("filter") !== "unassigned") return;
    setSelectedCategoryId("null");
    setStartDate("");
    setEndDate("");
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete("filter");
        return next;
      },
      { replace: true },
    );
  }, [searchParams, setSearchParams]);

  const accountIdsKey = Array.from(selectedAccountIds).sort((a, b) => a - b);

  // A selection describes rows the user can currently see, so it shouldn't
  // silently carry over ids that just scrolled out of the filtered view.
  useEffect(() => {
    setSelectedIds(new Set());
    // accountIdsKey is a fresh array each render; its *contents* are what
    // should drive the reset, so it's stringified for a stable dep.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startDate, endDate, accountIdsKey.join(","), selectedCategoryId, debouncedSearch]);

  const importMutation = useMutation({
    mutationFn: (rows: ImportRow[]) =>
      api<{ imported: number }>("/api/transactions/import-ynab", { method: "POST", body: { rows } }),
    onSuccess: () => {
      setImportOpen(false);
      void qc.invalidateQueries({ queryKey: ["transactions"] });
      void qc.invalidateQueries({ queryKey: ["accounts"] });
    },
  });

  const txnsQuery = useInfiniteQuery({
    queryKey: [
      "transactions",
      startDate,
      endDate,
      accountIdsKey,
      selectedCategoryId,
      debouncedSearch,
    ],
    queryFn: ({ pageParam }) =>
      fetchTransactionsPage({
        startDate,
        endDate,
        accountIds: accountIdsKey,
        categoryId: selectedCategoryId,
        q: debouncedSearch,
        cursor: pageParam,
      }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });

  const allTxns = useMemo(
    () => txnsQuery.data?.pages.flatMap((page) => page.items) ?? [],
    [txnsQuery.data],
  );

  const accountsQuery = useQuery<Account[]>({
    queryKey: ["accounts"],
    queryFn: () => api<Account[]>("/api/accounts"),
  });

  const groupsQuery = useQuery<CategoryGroup[]>({
    queryKey: ["category-groups"],
    queryFn: () => api<CategoryGroup[]>("/api/category-groups"),
  });

  // Powers the category picker's remaining-budget pill — always the
  // currently active month, regardless of the transaction's own date.
  const budgetQuery = useQuery<BudgetMonth>({
    queryKey: ["budget", currentMonth()],
    queryFn: () => api<BudgetMonth>(`/api/budget/${currentMonth()}`),
  });
  const budgetByCategoryId = new Map<number, CategoryBudgetInfo>(
    budgetQuery.data?.groups.flatMap((g) =>
      g.categories.map((c) => [c.id, { assigned_cents: c.assigned_cents, balance_cents: c.balance_cents }] as const),
    ) ?? [],
  );

  const accounts = accountsQuery.data ?? [];
  const flatCategories =
    groupsQuery.data?.flatMap((g) =>
      g.categories.map((c) => ({ ...c, groupId: g.id, groupName: g.name, groupScopeId: g.scope_id })),
    ) ?? [];

  const updateTxn = useMutation({
    mutationFn: ({ txnId, edit }: { txnId: number; edit: TransactionEdit }) =>
      api<Transaction>(`/api/transactions/${txnId}`, { method: "PATCH", body: edit }),
    onSuccess: () => {
      setEditingTxnId(null);
      setEditError(null);
      void qc.invalidateQueries({ queryKey: ["transactions"] });
      void qc.invalidateQueries({ queryKey: ["accounts"] });
      void qc.invalidateQueries({ queryKey: ["budget"] });
    },
    onError: (err) => setEditError(err instanceof Error ? err.message : "Update failed"),
  });

  const createTxn = useMutation({
    mutationFn: (input: TransactionCreateInput) =>
      api<Transaction>("/api/transactions", { method: "POST", body: input }),
    onSuccess: () => {
      setAddOpen(false);
      setAddError(null);
      invalidateAfterLink();
    },
    onError: (err) => setAddError(err instanceof Error ? err.message : "Could not add transaction"),
  });

  const deleteTxn = useMutation({
    mutationFn: (txnId: number) =>
      api(`/api/transactions/${txnId}`, { method: "DELETE" }),
    onSuccess: invalidateAfterLink,
  });

  const bulkDeleteTxns = useMutation({
    mutationFn: (ids: number[]) =>
      api<{ deleted: number }>("/api/transactions/bulk-delete", {
        method: "POST",
        body: { ids },
      }),
    onSuccess: () => {
      setSelectedIds(new Set());
      setBulkDeleteOpen(false);
      setBulkDeleteError(null);
      invalidateAfterLink();
    },
    onError: (err) =>
      setBulkDeleteError(err instanceof Error ? err.message : "Delete failed"),
  });

  const bulkSetCategory = useMutation({
    mutationFn: (categoryId: number | null) =>
      api<{ updated: number }>("/api/transactions/bulk-set-category", {
        method: "POST",
        body: { ids: Array.from(selectedIds), category_id: categoryId },
      }),
    onSuccess: () => {
      setSelectedIds(new Set());
      setBulkSetCategoryOpen(false);
      setBulkSetCategoryError(null);
      invalidateAfterLink();
    },
    onError: (err) =>
      setBulkSetCategoryError(err instanceof Error ? err.message : "Could not set the category"),
  });

  // A transfer touches two accounts, so the broad prefix has to go too.
  function invalidateAfterLink() {
    void qc.invalidateQueries({ queryKey: ["transactions"] });
    void qc.invalidateQueries({ queryKey: ["accounts"] });
    void qc.invalidateQueries({ queryKey: ["budget"] });
  }

  const unlinkTransfer = useMutation({
    mutationFn: (txnId: number) =>
      api(`/api/transactions/${txnId}/transfer-link`, { method: "DELETE" }),
    onSuccess: () => {
      setEditingTxnId(null);
      setEditError(null);
      invalidateAfterLink();
      void qc.invalidateQueries({ queryKey: ["transfer-suggestions"] });
    },
    onError: (err) =>
      setEditError(err instanceof Error ? err.message : "Could not unlink the transfer"),
  });

  function toggleAccount(id: number) {
    setSelectedAccountIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelected(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const allLoadedSelected = allTxns.length > 0 && allTxns.every((t) => selectedIds.has(t.id));
  const someLoadedSelected = allTxns.some((t) => selectedIds.has(t.id));
  const selectAllRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = someLoadedSelected && !allLoadedSelected;
    }
  }, [someLoadedSelected, allLoadedSelected]);

  function toggleSelectAllLoaded() {
    setSelectedIds(allLoadedSelected ? new Set() : new Set(allTxns.map((t) => t.id)));
  }

  const selectedTransactions = allTxns.filter((t) => selectedIds.has(t.id));

  const accountById = Object.fromEntries(accounts.map((a) => [a.id, a]));
  const categoryById = Object.fromEntries(flatCategories.map((c) => [c.id, c]));

  // Rows already arrive in date-desc order from the API, so grouping just
  // needs to notice when the date changes, not re-sort anything.
  const dateGroups: { date: string; txns: Transaction[] }[] = [];
  for (const t of allTxns) {
    const lastGroup = dateGroups[dateGroups.length - 1];
    if (lastGroup && lastGroup.date === t.date) {
      lastGroup.txns.push(t);
    } else {
      dateGroups.push({ date: t.date, txns: [t] });
    }
  }

  const editingTransaction =
    editingTxnId === null ? undefined : allTxns.find((t) => t.id === editingTxnId);
  const linkingTransaction =
    linking === null ? undefined : allTxns.find((t) => t.id === linking.txnId);
  const linkingAccount = linking === null ? undefined : accountById[linking.accountId];

  return (
    <div className="max-w-5xl space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Transactions</h1>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => {
              setSelectionMode((prev) => !prev);
              setSelectedIds(new Set());
            }}
            className="md:hidden border border-stone-300 dark:border-stone-600 text-stone-700 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 rounded-lg px-4 py-2 text-sm"
          >
            {selectionMode ? "Done" : "Select"}
          </button>
          <button
            type="button"
            onClick={() => {
              setAddError(null);
              setAddOpen(true);
            }}
            className="hidden md:inline-flex bg-indigo-600 hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600 text-white rounded-lg px-4 py-2 text-sm font-medium"
          >
            Add transaction
          </button>
          <button
            type="button"
            onClick={() => setImportOpen(true)}
            className="border border-stone-300 dark:border-stone-600 text-stone-700 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 rounded-lg px-4 py-2 text-sm"
          >
            Import YNAB
          </button>
        </div>
      </div>

      {/* Both of these render nothing when there's nothing to show, so
          neither can leave a gap in the page's vertical rhythm. */}
      <UnassignedTransactionsIsland />
      <TransferSuggestionsBanner
        startDate={startDate}
        endDate={endDate}
        accountById={accountById}
        onLinked={invalidateAfterLink}
      />

      {/* Filter panel */}
      <div className="bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 rounded-2xl p-5 space-y-4">
        <div className="flex flex-wrap gap-6 items-end">
          {/* Search */}
          <div className="space-y-1">
            <label className="text-sm font-medium text-stone-700 dark:text-stone-300">
              Search
            </label>
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Payee or memo"
              className="h-9 border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 text-sm"
            />
          </div>

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
                <option value="rta">Ready to Assign</option>
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

      {/* Bulk selection action bar */}
      {selectedIds.size > 0 && (
        <div className="flex items-center justify-between bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 rounded-2xl px-5 py-3">
          <span className="text-sm text-stone-700 dark:text-stone-300">
            {selectedIds.size} selected
          </span>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setSelectedIds(new Set())}
              className="text-sm text-stone-600 dark:text-stone-400 hover:underline px-2 py-1"
            >
              Clear
            </button>
            <button
              type="button"
              onClick={() => {
                setBulkSetCategoryError(null);
                setBulkSetCategoryOpen(true);
              }}
              className="border border-stone-300 dark:border-stone-600 text-stone-700 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 rounded-lg px-4 py-2 text-sm font-medium"
            >
              Set category
            </button>
            <button
              type="button"
              onClick={() => {
                setBulkDeleteError(null);
                setBulkDeleteOpen(true);
              }}
              className="bg-red-600 hover:bg-red-700 dark:bg-red-700 dark:hover:bg-red-600 text-white rounded-lg px-4 py-2 text-sm font-medium"
            >
              Delete selected
            </button>
          </div>
        </div>
      )}

      {/* Transaction list */}
      <div className="bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 rounded-2xl overflow-hidden">
        {txnsQuery.isLoading && (
          <div className="p-5 text-stone-500 dark:text-stone-400">Loading…</div>
        )}
        {!txnsQuery.isLoading && allTxns.length === 0 && (
          <div className="p-5 text-stone-500 dark:text-stone-400">No transactions found.</div>
        )}

        {/* Mobile: date-grouped, tappable cards */}
        {allTxns.length > 0 && (
          <div className="md:hidden">
            {dateGroups.map((group) => (
              <div key={group.date}>
                <div className="px-4 py-2 text-xs font-semibold uppercase text-stone-500 dark:text-stone-400 bg-stone-50 dark:bg-stone-800/50">
                  {formatDateHeading(group.date)}
                </div>
                {group.txns.map((t) => {
                  const account = accountById[t.account_id];
                  const cat = t.category_id !== null ? categoryById[t.category_id] : null;
                  const peerAccountName =
                    t.transfer_peer_account_id !== null
                      ? accountById[t.transfer_peer_account_id]?.name
                      : undefined;
                  return (
                    <MobileTransactionRow
                      key={t.id}
                      transaction={t}
                      account={account}
                      category={cat}
                      peerAccountName={peerAccountName}
                      selectionMode={selectionMode}
                      selected={selectedIds.has(t.id)}
                      onToggleSelect={() => toggleSelected(t.id)}
                      onOpen={() => {
                        setEditError(null);
                        setEditingTxnId(t.id);
                      }}
                    />
                  );
                })}
              </div>
            ))}
          </div>
        )}

        {allTxns.length > 0 && (
          <div className="hidden md:block overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs uppercase text-stone-500 dark:text-stone-400">
                <tr>
                  <th className="pl-4 pr-1 py-2">
                    <input
                      ref={selectAllRef}
                      type="checkbox"
                      checked={allLoadedSelected}
                      onChange={toggleSelectAllLoaded}
                      aria-label="Select all loaded transactions"
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
                {allTxns.map((t) => {
                  const account = accountById[t.account_id];
                  const cat = t.category_id !== null ? categoryById[t.category_id] : null;
                  const peerAccountName =
                    t.transfer_peer_account_id !== null
                      ? accountById[t.transfer_peer_account_id]?.name
                      : undefined;
                  const accentClass = needsCategory(t)
                    ? "border-l-4 border-amber-400 dark:border-amber-600"
                    : "border-l-4 border-indigo-200 dark:border-indigo-800";
                  return (
                    <tr key={t.id} className="border-t border-stone-100 dark:border-stone-800">
                      {/* The accent lives on this cell, not the <tr>: table rows don't
                          paint left borders under the default (non-collapsed) border model. */}
                      <td className={`pl-4 pr-1 py-2 border-l-4 ${accentClass}`}>
                        <input
                          type="checkbox"
                          checked={selectedIds.has(t.id)}
                          onChange={() => toggleSelected(t.id)}
                          aria-label={`Select transaction on ${t.date}`}
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
                        <CategoryBadge
                          transaction={t}
                          category={cat}
                          peerAccountName={peerAccountName}
                        />
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
                      <td className="px-5 py-2 text-right space-x-2 whitespace-nowrap">
                        <button
                          onClick={() => {
                            setEditError(null);
                            setEditingTxnId(t.id);
                          }}
                          className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline px-2 py-1"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => deleteTxn.mutate(t.id)}
                          title={
                            t.transfer_peer_id !== null
                              ? "Deletes both legs of the transfer"
                              : undefined
                          }
                          className="text-xs text-stone-500 dark:text-stone-400 hover:text-red-600 dark:hover:text-red-400 px-2 py-1"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {txnsQuery.hasNextPage && (
          <div className="p-4 text-center border-t border-stone-100 dark:border-stone-800">
            <button
              type="button"
              onClick={() => void txnsQuery.fetchNextPage()}
              disabled={txnsQuery.isFetchingNextPage}
              className="text-sm text-indigo-600 dark:text-indigo-400 hover:underline disabled:opacity-50"
            >
              {txnsQuery.isFetchingNextPage ? "Loading…" : "Load more"}
            </button>
          </div>
        )}
      </div>

      <BulkDeleteTransactionsConfirmModal
        selectedTransactions={selectedTransactions}
        isOpen={bulkDeleteOpen}
        onClose={() => {
          setBulkDeleteOpen(false);
          setBulkDeleteError(null);
        }}
        onConfirm={() => bulkDeleteTxns.mutate(Array.from(selectedIds))}
        isPending={bulkDeleteTxns.isPending}
        error={bulkDeleteError}
      />

      <BulkSetCategoryModal
        selectedTransactions={selectedTransactions}
        categories={flatCategories}
        budgetByCategoryId={budgetByCategoryId}
        isOpen={bulkSetCategoryOpen}
        onClose={() => {
          setBulkSetCategoryOpen(false);
          setBulkSetCategoryError(null);
        }}
        onConfirm={(categoryId) => bulkSetCategory.mutate(categoryId)}
        isPending={bulkSetCategory.isPending}
        error={bulkSetCategoryError}
      />

      {editingTransaction && (
        <EditTransactionModal
          transaction={editingTransaction}
          // Only categories in the transaction's own scope are valid — the
          // backend rejects the rest with a 422.
          categories={flatCategories.filter(
            (c) => c.groupScopeId === accountById[editingTransaction.account_id]?.scope_id,
          )}
          budgetByCategoryId={budgetByCategoryId}
          peerAccount={
            (editingTransaction.transfer_peer_account_id !== null
              ? accountById[editingTransaction.transfer_peer_account_id]
              : undefined) ?? null
          }
          transferTargets={accounts.filter(
            (a) => a.id !== editingTransaction.account_id && !a.closed,
          )}
          isOpen={true}
          onClose={() => {
            setEditingTxnId(null);
            setEditError(null);
          }}
          onSave={(edit) => updateTxn.mutate({ txnId: editingTransaction.id, edit })}
          onPickTransferTarget={(targetAccountId) => {
            setEditingTxnId(null);
            setEditError(null);
            setLinking({ txnId: editingTransaction.id, accountId: targetAccountId });
          }}
          onUnlinkTransfer={() => unlinkTransfer.mutate(editingTransaction.id)}
          onDelete={() => deleteTxn.mutate(editingTransaction.id)}
          isPending={updateTxn.isPending || unlinkTransfer.isPending}
          isDeletePending={deleteTxn.isPending}
          error={editError}
        />
      )}

      {linkingTransaction && linkingAccount && (
        <LinkTransferModal
          transaction={linkingTransaction}
          targetAccount={linkingAccount}
          onClose={() => setLinking(null)}
          onLinked={() => {
            setLinking(null);
            invalidateAfterLink();
          }}
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

      <AddTransactionModal
        accounts={accounts}
        categoriesByScope={flatCategories}
        budgetByCategoryId={budgetByCategoryId}
        isOpen={addOpen}
        onClose={() => {
          setAddOpen(false);
          setAddError(null);
        }}
        onSave={(input) => createTxn.mutate(input)}
        isPending={createTxn.isPending}
        error={addError}
      />

      {/* Mobile-only quick add, kept clear of any bottom chrome since the app has no bottom nav. */}
      <button
        type="button"
        onClick={() => {
          setAddError(null);
          setAddOpen(true);
        }}
        aria-label="Add transaction"
        className="md:hidden fixed bottom-6 right-6 z-20 h-14 w-14 rounded-full bg-indigo-600 hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600 text-white text-3xl leading-none shadow-lg flex items-center justify-center"
      >
        +
      </button>
    </div>
  );
}
