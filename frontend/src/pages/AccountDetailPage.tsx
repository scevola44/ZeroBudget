import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type {
  Account,
  CategoryGroup,
  Payee,
  Transaction,
  TransactionListResponse,
  Transfer,
} from "../api/types";
import {
  EditTransactionModal,
  type TransactionEdit,
} from "../components/EditTransactionModal";
import { LinkTransferModal } from "../components/LinkTransferModal";
import { ScopeChip } from "../components/ScopeChip";
import {
  emptySplitLine,
  parseSplitLines,
  splitRemainingCents,
  SplitEditor,
  type SplitLineInput,
} from "../components/SplitEditor";
import { partitionSuggested } from "../lib/categorySuggestions";
import { todayISO } from "../lib/dates";
import { formatCents, parseAmountToCents } from "../lib/money";
import { useDebouncedValue } from "../lib/useDebouncedValue";

// Marks a "Transfer : <account>" choice in the category picker, YNAB-style.
const TRANSFER_OPTION_PREFIX = "transfer:";

function transferTargetId(categoryChoice: string): number | null {
  if (!categoryChoice.startsWith(TRANSFER_OPTION_PREFIX)) return null;
  return Number(categoryChoice.slice(TRANSFER_OPTION_PREFIX.length));
}

export function AccountDetailPage() {
  const { id } = useParams<{ id: string }>();
  const accountId = Number(id);
  const qc = useQueryClient();

  const accountsQuery = useQuery<Account[]>({
    queryKey: ["accounts"],
    queryFn: () => api<Account[]>("/api/accounts"),
  });
  const account = accountsQuery.data?.find((a) => a.id === accountId);

  // No pagination UI on this page (unlike /transactions) — the API's max
  // page size stands in for "all of this account's history" so it doesn't
  // silently truncate past the default page size.
  const txnsQuery = useQuery<TransactionListResponse>({
    queryKey: ["transactions", accountId],
    queryFn: () =>
      api<TransactionListResponse>(`/api/transactions?account_id=${accountId}&limit=500`),
    enabled: Number.isFinite(accountId),
  });
  const txns = txnsQuery.data?.items ?? [];

  const groupsQuery = useQuery<CategoryGroup[]>({
    queryKey: ["category-groups"],
    queryFn: () => api<CategoryGroup[]>("/api/category-groups"),
  });

  const payeesQuery = useQuery<Payee[]>({
    queryKey: ["payees"],
    queryFn: () => api<Payee[]>("/api/payees"),
  });

  // Categories visible in the dropdown are only those whose group scope
  // matches the account's scope — otherwise the backend rejects with 422.
  const flatCategories =
    groupsQuery.data?.flatMap((g) =>
      g.categories.map((c) => ({ ...c, groupName: g.name, groupScope: g.scope })),
    ) ?? [];
  const eligibleCategories = account
    ? flatCategories.filter((c) => c.groupScope === account.scope)
    : flatCategories;

  const [date, setDate] = useState(todayISO);
  const [payee, setPayee] = useState("");
  const [memo, setMemo] = useState("");
  const [amount, setAmount] = useState("");
  const [categoryId, setCategoryId] = useState<string>("");
  // Whether the user has picked a category themselves this entry, so a
  // suggestion arriving afterward never overrides a deliberate choice.
  const [categoryTouched, setCategoryTouched] = useState(false);
  const [splitMode, setSplitMode] = useState(false);
  const [splitLines, setSplitLines] = useState<SplitLineInput[]>(() => [
    emptySplitLine(),
    emptySplitLine(),
  ]);
  const [formError, setFormError] = useState<string | null>(null);
  const [editingCategoryTxnId, setEditingCategoryTxnId] = useState<number | null>(null);
  // The existing row being linked to a transfer, and the account holding its
  // other leg — set together when "Transfer : <account>" is picked on a row.
  const [linking, setLinking] = useState<{ txnId: number; accountId: number } | null>(
    null,
  );
  const [editingTxnId, setEditingTxnId] = useState<number | null>(null);
  const [editError, setEditError] = useState<string | null>(null);
  // Failures from the in-row actions, which have no modal of their own to
  // surface them.
  const [rowActionError, setRowActionError] = useState<string | null>(null);
  const [editingBalance, setEditingBalance] = useState(false);
  const [balanceInput, setBalanceInput] = useState("");
  const [balanceError, setBalanceError] = useState<string | null>(null);

  const accountById = new Map((accountsQuery.data ?? []).map((a) => [a.id, a]));
  const transferTargets = (accountsQuery.data ?? []).filter(
    (a) => a.id !== accountId && !a.closed,
  );

  const debouncedPayee = useDebouncedValue(payee, 300);
  const suggestionsQuery = useQuery<number[]>({
    queryKey: ["category-suggestions", accountId, debouncedPayee],
    queryFn: () =>
      api<number[]>(
        `/api/transactions/category-suggestions?account_id=${accountId}&payee=${encodeURIComponent(debouncedPayee)}`,
      ),
    enabled: Number.isFinite(accountId) && debouncedPayee.trim().length > 0,
  });
  const suggestedCategoryIds = suggestionsQuery.data ?? [];
  const { suggested: suggestedCategories, rest: otherCategories } = partitionSuggested(
    eligibleCategories,
    suggestedCategoryIds,
  );

  // Track the top suggestion into the field as the payee changes, but stop
  // the moment the user picks a category themselves — never override a
  // deliberate choice, including by leaving a stale guess in place once the
  // payee no longer matches it.
  useEffect(() => {
    if (categoryTouched) return;
    setCategoryId(suggestedCategoryIds.length > 0 ? String(suggestedCategoryIds[0]) : "");
  }, [suggestedCategoryIds, categoryTouched]);

  const editingTransaction =
    editingTxnId === null ? undefined : txns.find((t) => t.id === editingTxnId);

  const linkingTransaction =
    linking === null ? undefined : txns.find((t) => t.id === linking.txnId);
  const linkingAccount = linking === null ? undefined : accountById.get(linking.accountId);

  function peerAccountOf(txn: Transaction): Account | undefined {
    return txn.transfer_peer_account_id === null
      ? undefined
      : accountById.get(txn.transfer_peer_account_id);
  }

  // A transfer touches a second account, so the broad prefix has to go too.
  function invalidateAfterChange() {
    void qc.invalidateQueries({ queryKey: ["transactions"] });
    void qc.invalidateQueries({ queryKey: ["accounts"] });
    void qc.invalidateQueries({ queryKey: ["budget"] });
    void qc.invalidateQueries({ queryKey: ["payees"] });
  }

  const createTxn = useMutation({
    mutationFn: (body: {
      account_id: number;
      category_id: number | null;
      date: string;
      payee: string;
      memo: string;
      amount_cents: number;
      splits?: { category_id: number | null; amount_cents: number; memo: string }[];
    }) => api<Transaction>("/api/transactions", { method: "POST", body }),
    onSuccess: () => {
      resetForm();
      invalidateAfterChange();
    },
  });

  const createTransfer = useMutation({
    mutationFn: (body: {
      from_account_id: number;
      to_account_id: number;
      date: string;
      payee: string;
      memo: string;
      amount_cents: number;
    }) => api<Transfer>("/api/transactions/transfer", { method: "POST", body }),
    onSuccess: () => {
      resetForm();
      invalidateAfterChange();
    },
    onError: (err) =>
      setFormError(err instanceof Error ? err.message : "Could not create the transfer"),
  });

  const deleteTxn = useMutation({
    mutationFn: (txnId: number) =>
      api(`/api/transactions/${txnId}`, { method: "DELETE" }),
    onSuccess: invalidateAfterChange,
  });

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

  const setBalance = useMutation({
    mutationFn: (balance_cents: number) =>
      api<Account>(`/api/accounts/${accountId}/balance`, {
        method: "POST",
        body: { balance_cents },
      }),
    onSuccess: () => {
      setEditingBalance(false);
      void qc.invalidateQueries({ queryKey: ["accounts"] });
      void qc.invalidateQueries({ queryKey: ["transactions", accountId] });
      void qc.invalidateQueries({ queryKey: ["budget"] });
    },
  });

  const updateCategory = useMutation({
    mutationFn: ({ txnId, categoryId: catId }: { txnId: number; categoryId: number | null }) =>
      api<Transaction>(`/api/transactions/${txnId}`, {
        method: "PATCH",
        body: { category_id: catId },
      }),
    onSuccess: () => {
      invalidateAfterChange();
      setEditingCategoryTxnId(null);
    },
    onError: (err) =>
      setRowActionError(err instanceof Error ? err.message : "Could not set the category"),
  });

  const unlinkTransfer = useMutation({
    mutationFn: (txnId: number) =>
      api(`/api/transactions/${txnId}/transfer-link`, { method: "DELETE" }),
    onSuccess: () => {
      invalidateAfterChange();
      void qc.invalidateQueries({ queryKey: ["transfer-suggestions"] });
    },
    onError: (err) =>
      setRowActionError(
        err instanceof Error ? err.message : "Could not unlink the transfer",
      ),
  });

  function resetForm() {
    setPayee("");
    setMemo("");
    setAmount("");
    setCategoryId("");
    setCategoryTouched(false);
    setSplitMode(false);
    setSplitLines([emptySplitLine(), emptySplitLine()]);
  }

  function onBalanceSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBalanceError(null);
    const cents = parseAmountToCents(balanceInput);
    if (cents === null) {
      setBalanceError("Enter a valid amount.");
      return;
    }
    setBalance.mutate(cents);
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    const cents = parseAmountToCents(amount);
    if (cents === null) {
      setFormError("Enter a valid amount (use '-' for outflow).");
      return;
    }

    if (splitMode) {
      const splits = parseSplitLines(splitLines);
      if (splits === null || splits.length < 2) {
        setFormError("Enter a valid amount for every split line (at least two).");
        return;
      }
      if (splitRemainingCents(amount, splitLines) !== 0) {
        setFormError("Split lines must add up to the transaction amount.");
        return;
      }
      createTxn.mutate({
        account_id: accountId,
        category_id: null,
        date,
        payee,
        memo,
        amount_cents: cents,
        splits,
      });
      return;
    }

    const peerAccountId = transferTargetId(categoryId);
    if (peerAccountId !== null) {
      if (cents === 0) {
        setFormError("A transfer needs a non-zero amount.");
        return;
      }
      // The sign says which way the money moves relative to this account.
      const movingOut = cents < 0;
      createTransfer.mutate({
        from_account_id: movingOut ? accountId : peerAccountId,
        to_account_id: movingOut ? peerAccountId : accountId,
        date,
        payee,
        memo,
        amount_cents: Math.abs(cents),
      });
      return;
    }

    createTxn.mutate({
      account_id: accountId,
      category_id: categoryId ? Number(categoryId) : null,
      date,
      payee,
      memo,
      amount_cents: cents,
    });
  }

  return (
    <div className="max-w-4xl space-y-6">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold">
            {account ? account.name : "Account"}
          </h1>
          {account && <ScopeChip scope={account.scope} />}
        </div>
        <Link
          to="/accounts"
          className="text-sm text-indigo-600 dark:text-indigo-400 hover:underline"
        >
          ← All accounts
        </Link>
      </header>

      {account && (
        <div className="bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 rounded-2xl px-5 py-4">
          <div className="flex items-center justify-between">
            <div className="text-xs uppercase tracking-wide text-stone-500 dark:text-stone-400">Balance</div>
            {!editingBalance && (
              <button
                onClick={() => {
                  setBalanceInput((account.balance_cents / 100).toFixed(2));
                  setBalanceError(null);
                  setEditingBalance(true);
                }}
                className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline"
              >
                Edit balance
              </button>
            )}
          </div>
          {editingBalance ? (
            <form onSubmit={onBalanceSubmit} className="flex items-end gap-2 mt-1">
              <div className="space-y-1">
                <input
                  autoFocus
                  value={balanceInput}
                  onChange={(e) => setBalanceInput(e.target.value)}
                  inputMode="decimal"
                  className="w-40 border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-2 text-right tabular-nums text-lg"
                />
                {balanceError && (
                  <p className="text-sm text-red-600 dark:text-red-400">{balanceError}</p>
                )}
              </div>
              <button
                type="submit"
                disabled={setBalance.isPending}
                className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 dark:bg-indigo-500 dark:hover:bg-indigo-600 text-white font-medium rounded-lg px-4 py-2"
              >
                Save
              </button>
              <button
                type="button"
                onClick={() => setEditingBalance(false)}
                className="text-stone-600 dark:text-stone-400 hover:underline px-2 py-2"
              >
                Cancel
              </button>
            </form>
          ) : (
            <div className="text-2xl font-semibold tabular-nums">
              {formatCents(account.balance_cents)}
            </div>
          )}
        </div>
      )}

      <form
        className="bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 rounded-2xl p-5 grid grid-cols-1 md:grid-cols-6 gap-3 items-end"
        onSubmit={onSubmit}
      >
        <div className="space-y-1 md:col-span-1">
          <label className="text-sm font-medium text-stone-700 dark:text-stone-300">Date</label>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            required
            className="w-full border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-2"
          />
        </div>
        <div className="space-y-1 md:col-span-2">
          <label className="text-sm font-medium text-stone-700 dark:text-stone-300">Payee</label>
          <input
            value={payee}
            onChange={(e) => setPayee(e.target.value)}
            placeholder="e.g. Supermarket"
            list="payee-options"
            className="w-full border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-2"
          />
          <datalist id="payee-options">
            {(payeesQuery.data ?? []).map((p) => (
              <option key={p.id} value={p.name} />
            ))}
          </datalist>
        </div>
        <div className={`space-y-1 ${splitMode ? "md:col-span-5" : "md:col-span-2"}`}>
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-stone-700 dark:text-stone-300">Category</label>
            <button
              type="button"
              onClick={() => setSplitMode((m) => !m)}
              className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline"
            >
              {splitMode ? "Use single category" : "Split into multiple categories"}
            </button>
          </div>
          {splitMode ? (
            <SplitEditor
              categories={eligibleCategories}
              totalAmountText={amount}
              lines={splitLines}
              onChange={setSplitLines}
            />
          ) : (
            <div className="relative">
              <select
                value={categoryId}
                onChange={(e) => {
                  setCategoryTouched(true);
                  setCategoryId(e.target.value);
                }}
                className="h-9 w-full appearance-none border border-stone-300 dark:border-stone-600 rounded-lg pl-3 pr-8 bg-white dark:bg-stone-900"
              >
                <option value="">— Unassigned (inflow) —</option>
                {suggestedCategories.length > 0 && (
                  <optgroup label="Suggested">
                    {suggestedCategories.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.groupName} › {c.name}
                      </option>
                    ))}
                  </optgroup>
                )}
                {otherCategories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.groupName} › {c.name}
                  </option>
                ))}
                {transferTargets.length > 0 && (
                  <optgroup label="Transfer">
                    {transferTargets.map((a) => (
                      <option key={a.id} value={`${TRANSFER_OPTION_PREFIX}${a.id}`}>
                        Transfer : {a.name}
                      </option>
                    ))}
                  </optgroup>
                )}
              </select>
              <div className="pointer-events-none absolute inset-y-0 right-2 flex items-center text-stone-400 dark:text-stone-500">
                <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 6l4 4 4-4" />
                </svg>
              </div>
            </div>
          )}
        </div>
        <div className="space-y-1 md:col-span-1">
          <label className="text-sm font-medium text-stone-700 dark:text-stone-300">Amount</label>
          <input
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            required
            inputMode="decimal"
            placeholder="-12.34"
            className="w-full border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-2 text-right tabular-nums"
          />
        </div>
        <div className="space-y-1 md:col-span-5">
          <label className="text-sm font-medium text-stone-700 dark:text-stone-300">Memo</label>
          <input
            value={memo}
            onChange={(e) => setMemo(e.target.value)}
            className="w-full border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-2"
          />
        </div>
        <button
          type="submit"
          disabled={createTxn.isPending || createTransfer.isPending}
          className="md:col-span-1 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 dark:bg-indigo-500 dark:hover:bg-indigo-600 text-white font-medium rounded-lg px-4 py-2"
        >
          Add
        </button>
        {transferTargetId(categoryId) !== null && (
          <p className="md:col-span-6 text-sm text-stone-500 dark:text-stone-400">
            A negative amount sends money out of this account; a positive amount brings it in.
          </p>
        )}
        {formError && (
          <p className="md:col-span-6 text-sm text-red-600 dark:text-red-400">{formError}</p>
        )}
      </form>

      {rowActionError && (
        <p className="text-sm text-red-600 dark:text-red-400">{rowActionError}</p>
      )}

      <div className="bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 rounded-2xl overflow-hidden">
        {txnsQuery.isLoading && <div className="p-5 text-stone-500 dark:text-stone-400">Loading…</div>}
        {!txnsQuery.isLoading && txns.length === 0 && (
          <div className="p-5 text-stone-500 dark:text-stone-400">No transactions yet.</div>
        )}
        {txns.length > 0 && (
          <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase text-stone-500 dark:text-stone-400">
              <tr>
                <th className="text-left px-5 py-2">Date</th>
                <th className="text-left px-5 py-2">Payee</th>
                <th className="text-left px-5 py-2">Category</th>
                <th className="hidden sm:table-cell text-left px-5 py-2">Memo</th>
                <th className="text-right px-5 py-2">Amount</th>
                <th className="px-5 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {txns.map((t) => {
                const cat = flatCategories.find((c) => c.id === t.category_id);
                const peerAccount = peerAccountOf(t);
                return (
                  <tr key={t.id} className="border-t border-stone-100 dark:border-stone-800">
                    <td className="px-5 py-2 text-stone-600 dark:text-stone-400">{t.date}</td>
                    <td className="px-5 py-2">{t.payee || <span className="text-stone-400 dark:text-stone-500">—</span>}</td>
                    <td className="px-5 py-2">
                      {t.transfer_peer_id !== null ? (
                        <span className="text-stone-600 dark:text-stone-300">
                          Transfer : {peerAccount?.name ?? "another account"}
                        </span>
                      ) : t.splits.length > 0 ? (
                        <button
                          className="text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 rounded px-1 py-0.5 text-left w-full"
                          onClick={() => {
                            setEditError(null);
                            setEditingTxnId(t.id);
                          }}
                          title="Edit splits"
                        >
                          Split ({t.splits.length})
                        </button>
                      ) : editingCategoryTxnId === t.id ? (
                        <div className="relative">
                          <select
                            autoFocus
                            defaultValue={t.category_id ?? ""}
                            onChange={(e) => {
                              setRowActionError(null);
                              const targetAccountId = transferTargetId(e.target.value);
                              if (targetAccountId !== null) {
                                setLinking({ txnId: t.id, accountId: targetAccountId });
                                setEditingCategoryTxnId(null);
                                return;
                              }
                              const newId = e.target.value === "" ? null : Number(e.target.value);
                              updateCategory.mutate({ txnId: t.id, categoryId: newId });
                            }}
                            onBlur={() => setEditingCategoryTxnId(null)}
                            onKeyDown={(e) => { if (e.key === "Escape") setEditingCategoryTxnId(null); }}
                            className="h-9 w-full appearance-none border border-indigo-300 dark:border-indigo-500 bg-white dark:bg-stone-900 rounded-md pl-2 pr-6 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                          >
                            <option value="">— Unassigned —</option>
                            {eligibleCategories.map((c) => (
                              <option key={c.id} value={c.id}>
                                {c.groupName} › {c.name}
                              </option>
                            ))}
                            {transferTargets.length > 0 && (
                              <optgroup label="Transfer">
                                {transferTargets.map((a) => (
                                  <option
                                    key={a.id}
                                    value={`${TRANSFER_OPTION_PREFIX}${a.id}`}
                                  >
                                    Transfer : {a.name}
                                  </option>
                                ))}
                              </optgroup>
                            )}
                          </select>
                          <div className="pointer-events-none absolute inset-y-0 right-1 flex items-center text-indigo-500">
                            <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                              <path d="M4 6l4 4 4-4" />
                            </svg>
                          </div>
                        </div>
                      ) : (
                        <button
                          className="text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 rounded px-1 py-0.5 text-left w-full"
                          onClick={() => setEditingCategoryTxnId(t.id)}
                        >
                          {cat ? `${cat.groupName} › ${cat.name}` : <span className="text-stone-400 dark:text-stone-500">Unassigned</span>}
                        </button>
                      )}
                    </td>
                    <td className="hidden sm:table-cell px-5 py-2 text-stone-500 dark:text-stone-400">{t.memo}</td>
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
                      {t.transfer_peer_id !== null && (
                        <button
                          onClick={() => {
                            setRowActionError(null);
                            unlinkTransfer.mutate(t.id);
                          }}
                          title="Keeps both transactions, just not as a transfer"
                          className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline px-2 py-1"
                        >
                          Unlink
                        </button>
                      )}
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
      </div>

      {editingTransaction && (
        <EditTransactionModal
          transaction={editingTransaction}
          categories={eligibleCategories}
          peerAccount={peerAccountOf(editingTransaction) ?? null}
          isOpen={true}
          onClose={() => {
            setEditingTxnId(null);
            setEditError(null);
          }}
          onSave={(edit) => updateTxn.mutate({ txnId: editingTransaction.id, edit })}
          onUnlinkTransfer={() => {
            setEditingTxnId(null);
            setRowActionError(null);
            unlinkTransfer.mutate(editingTransaction.id);
          }}
          isPending={updateTxn.isPending}
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
            invalidateAfterChange();
          }}
        />
      )}
    </div>
  );
}
