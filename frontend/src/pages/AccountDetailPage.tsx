import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { Account, CategoryGroup, Scope, Transaction } from "../api/types";
import { scopeLabel } from "../api/types";
import { todayISO } from "../lib/dates";
import { formatCents, parseAmountToCents } from "../lib/money";

function ScopeChip({ scope }: { scope: Scope }) {
  const cls =
    scope === "shared"
      ? "bg-violet-100 text-violet-800 dark:bg-violet-900/50 dark:text-violet-200"
      : "bg-sky-100 text-sky-800 dark:bg-sky-900/50 dark:text-sky-200";
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}>
      {scopeLabel(scope)}
    </span>
  );
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

  const txnsQuery = useQuery<Transaction[]>({
    queryKey: ["transactions", accountId],
    queryFn: () => api<Transaction[]>(`/api/transactions?account_id=${accountId}`),
    enabled: Number.isFinite(accountId),
  });

  const groupsQuery = useQuery<CategoryGroup[]>({
    queryKey: ["category-groups"],
    queryFn: () => api<CategoryGroup[]>("/api/category-groups"),
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
  const [formError, setFormError] = useState<string | null>(null);
  const [editingCategoryTxnId, setEditingCategoryTxnId] = useState<number | null>(null);

  const createTxn = useMutation({
    mutationFn: (body: {
      account_id: number;
      category_id: number | null;
      date: string;
      payee: string;
      memo: string;
      amount_cents: number;
    }) => api<Transaction>("/api/transactions", { method: "POST", body }),
    onSuccess: () => {
      setPayee("");
      setMemo("");
      setAmount("");
      setCategoryId("");
      void qc.invalidateQueries({ queryKey: ["transactions", accountId] });
      void qc.invalidateQueries({ queryKey: ["accounts"] });
      void qc.invalidateQueries({ queryKey: ["budget"] });
    },
  });

  const deleteTxn = useMutation({
    mutationFn: (txnId: number) =>
      api(`/api/transactions/${txnId}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["transactions", accountId] });
      void qc.invalidateQueries({ queryKey: ["accounts"] });
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
      void qc.invalidateQueries({ queryKey: ["transactions", accountId] });
      void qc.invalidateQueries({ queryKey: ["accounts"] });
      void qc.invalidateQueries({ queryKey: ["budget"] });
      setEditingCategoryTxnId(null);
    },
  });

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    const cents = parseAmountToCents(amount);
    if (cents === null) {
      setFormError("Enter a valid amount (use '-' for outflow).");
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
          <div className="text-xs uppercase tracking-wide text-stone-500 dark:text-stone-400">Balance</div>
          <div className="text-2xl font-semibold tabular-nums">
            {formatCents(account.balance_cents)}
          </div>
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
            className="w-full border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-2"
          />
        </div>
        <div className="space-y-1 md:col-span-2">
          <label className="text-sm font-medium text-stone-700 dark:text-stone-300">Category</label>
          <select
            value={categoryId}
            onChange={(e) => setCategoryId(e.target.value)}
            className="w-full border border-stone-300 dark:border-stone-600 rounded-lg px-3 py-2 bg-white dark:bg-stone-900"
          >
            <option value="">— Unassigned (inflow) —</option>
            {eligibleCategories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.groupName} › {c.name}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1 md:col-span-1">
          <label className="text-sm font-medium text-stone-700 dark:text-stone-300">Amount</label>
          <input
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            required
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
          disabled={createTxn.isPending}
          className="md:col-span-1 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 dark:bg-indigo-500 dark:hover:bg-indigo-600 text-white font-medium rounded-lg px-4 py-2"
        >
          Add
        </button>
        {formError && (
          <p className="md:col-span-6 text-sm text-red-600 dark:text-red-400">{formError}</p>
        )}
      </form>

      <div className="bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 rounded-2xl overflow-hidden">
        {txnsQuery.isLoading && <div className="p-5 text-stone-500 dark:text-stone-400">Loading…</div>}
        {txnsQuery.data && txnsQuery.data.length === 0 && (
          <div className="p-5 text-stone-500 dark:text-stone-400">No transactions yet.</div>
        )}
        {txnsQuery.data && txnsQuery.data.length > 0 && (
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
              {txnsQuery.data.map((t) => {
                const cat = flatCategories.find((c) => c.id === t.category_id);
                return (
                  <tr key={t.id} className="border-t border-stone-100 dark:border-stone-800">
                    <td className="px-5 py-2 text-stone-600 dark:text-stone-400">{t.date}</td>
                    <td className="px-5 py-2">{t.payee || <span className="text-stone-400 dark:text-stone-500">—</span>}</td>
                    <td className="px-5 py-2">
                      {editingCategoryTxnId === t.id ? (
                        <select
                          autoFocus
                          defaultValue={t.category_id ?? ""}
                          onChange={(e) => {
                            const newId = e.target.value === "" ? null : Number(e.target.value);
                            updateCategory.mutate({ txnId: t.id, categoryId: newId });
                          }}
                          onBlur={() => setEditingCategoryTxnId(null)}
                          onKeyDown={(e) => { if (e.key === "Escape") setEditingCategoryTxnId(null); }}
                          className="border border-indigo-300 dark:border-indigo-500 bg-white dark:bg-stone-900 rounded-md px-2 py-0.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                        >
                          <option value="">— Unassigned —</option>
                          {flatCategories.map((c) => (
                            <option key={c.id} value={c.id}>
                              {c.groupName} › {c.name}
                            </option>
                          ))}
                        </select>
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
                    <td className="px-5 py-2 text-right">
                      <button
                        onClick={() => deleteTxn.mutate(t.id)}
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
    </div>
  );
}
