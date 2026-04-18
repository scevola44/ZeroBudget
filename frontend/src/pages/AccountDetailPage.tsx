import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { Account, CategoryGroup, Transaction } from "../api/types";
import { todayISO } from "../lib/dates";
import { formatCents, parseAmountToCents } from "../lib/money";

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

  const flatCategories =
    groupsQuery.data?.flatMap((g) =>
      g.categories.map((c) => ({ ...c, groupName: g.name })),
    ) ?? [];

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
        <h1 className="text-2xl font-semibold">
          {account ? account.name : "Account"}
        </h1>
        <Link
          to="/accounts"
          className="text-sm text-indigo-600 hover:underline"
        >
          ← All accounts
        </Link>
      </header>

      {account && (
        <div className="bg-white border border-slate-200 rounded-2xl px-5 py-4">
          <div className="text-xs uppercase tracking-wide text-slate-500">Balance</div>
          <div className="text-2xl font-semibold tabular-nums">
            {formatCents(account.balance_cents)}
          </div>
        </div>
      )}

      <form
        className="bg-white border border-slate-200 rounded-2xl p-5 grid grid-cols-1 md:grid-cols-6 gap-3 items-end"
        onSubmit={onSubmit}
      >
        <div className="space-y-1 md:col-span-1">
          <label className="text-sm font-medium text-slate-700">Date</label>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            required
            className="w-full border border-slate-300 rounded-lg px-3 py-2"
          />
        </div>
        <div className="space-y-1 md:col-span-2">
          <label className="text-sm font-medium text-slate-700">Payee</label>
          <input
            value={payee}
            onChange={(e) => setPayee(e.target.value)}
            placeholder="e.g. Supermarket"
            className="w-full border border-slate-300 rounded-lg px-3 py-2"
          />
        </div>
        <div className="space-y-1 md:col-span-2">
          <label className="text-sm font-medium text-slate-700">Category</label>
          <select
            value={categoryId}
            onChange={(e) => setCategoryId(e.target.value)}
            className="w-full border border-slate-300 rounded-lg px-3 py-2 bg-white"
          >
            <option value="">— Unassigned (inflow) —</option>
            {flatCategories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.groupName} › {c.name}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1 md:col-span-1">
          <label className="text-sm font-medium text-slate-700">Amount</label>
          <input
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            required
            placeholder="-12.34"
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-right tabular-nums"
          />
        </div>
        <div className="space-y-1 md:col-span-5">
          <label className="text-sm font-medium text-slate-700">Memo</label>
          <input
            value={memo}
            onChange={(e) => setMemo(e.target.value)}
            className="w-full border border-slate-300 rounded-lg px-3 py-2"
          />
        </div>
        <button
          type="submit"
          disabled={createTxn.isPending}
          className="md:col-span-1 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white font-medium rounded-lg px-4 py-2"
        >
          Add
        </button>
        {formError && (
          <p className="md:col-span-6 text-sm text-red-600">{formError}</p>
        )}
      </form>

      <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
        {txnsQuery.isLoading && <div className="p-5 text-slate-500">Loading…</div>}
        {txnsQuery.data && txnsQuery.data.length === 0 && (
          <div className="p-5 text-slate-500">No transactions yet.</div>
        )}
        {txnsQuery.data && txnsQuery.data.length > 0 && (
          <table className="w-full text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr>
                <th className="text-left px-5 py-2">Date</th>
                <th className="text-left px-5 py-2">Payee</th>
                <th className="text-left px-5 py-2">Category</th>
                <th className="text-left px-5 py-2">Memo</th>
                <th className="text-right px-5 py-2">Amount</th>
                <th className="px-5 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {txnsQuery.data.map((t) => {
                const cat = flatCategories.find((c) => c.id === t.category_id);
                return (
                  <tr key={t.id} className="border-t border-slate-100">
                    <td className="px-5 py-2 text-slate-600">{t.date}</td>
                    <td className="px-5 py-2">{t.payee || <span className="text-slate-400">—</span>}</td>
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
                          className="border border-indigo-300 rounded-md px-2 py-0.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
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
                          className="text-slate-600 hover:bg-slate-100 rounded px-1 py-0.5 text-left w-full"
                          onClick={() => setEditingCategoryTxnId(t.id)}
                        >
                          {cat ? `${cat.groupName} › ${cat.name}` : <span className="text-slate-400">Unassigned</span>}
                        </button>
                      )}
                    </td>
                    <td className="px-5 py-2 text-slate-500">{t.memo}</td>
                    <td
                      className={`px-5 py-2 text-right tabular-nums ${
                        t.amount_cents >= 0 ? "text-emerald-700" : "text-slate-900"
                      }`}
                    >
                      {formatCents(t.amount_cents)}
                    </td>
                    <td className="px-5 py-2 text-right">
                      <button
                        onClick={() => deleteTxn.mutate(t.id)}
                        className="text-xs text-slate-500 hover:text-red-600"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
