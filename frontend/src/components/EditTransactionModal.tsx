import { useEffect, useState } from "react";

import type { Account, Transaction } from "../api/types";
import { parseAmountToCents } from "../lib/money";

export type TransactionEdit = {
  date: string;
  payee: string;
  memo: string;
  amount_cents: number;
  category_id: number | null;
};

export type CategoryChoice = { id: number; name: string; groupName: string };

export function EditTransactionModal({
  transaction,
  categories,
  peerAccount,
  isOpen,
  onClose,
  onSave,
  isPending,
  error,
}: {
  transaction: Transaction;
  /** Already narrowed to the account's scope by the caller. */
  categories: CategoryChoice[];
  /** The other leg's account, when this transaction is a transfer. */
  peerAccount: Account | null;
  isOpen: boolean;
  onClose: () => void;
  onSave: (edit: TransactionEdit) => void;
  isPending: boolean;
  error: string | null;
}) {
  const [date, setDate] = useState(transaction.date);
  const [payee, setPayee] = useState(transaction.payee);
  const [memo, setMemo] = useState(transaction.memo);
  const [amount, setAmount] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [amountError, setAmountError] = useState<string | null>(null);

  const isTransfer = transaction.transfer_peer_id !== null;

  useEffect(() => {
    if (!isOpen) return;
    setDate(transaction.date);
    setPayee(transaction.payee);
    setMemo(transaction.memo);
    setAmount((transaction.amount_cents / 100).toFixed(2));
    setCategoryId(transaction.category_id === null ? "" : String(transaction.category_id));
    setAmountError(null);
  }, [isOpen, transaction]);

  if (!isOpen) return null;

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const cents = parseAmountToCents(amount);
    if (cents === null) {
      setAmountError("Enter a valid amount (use '-' for outflow).");
      return;
    }
    setAmountError(null);
    onSave({
      date,
      payee,
      memo,
      amount_cents: cents,
      category_id: categoryId ? Number(categoryId) : null,
    });
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-white dark:bg-stone-900 rounded-2xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between px-6 py-4 border-b border-stone-200 dark:border-stone-700">
          <h2 className="text-lg font-semibold">
            {isTransfer ? "Edit transfer" : "Edit transaction"}
          </h2>
          <button
            type="button"
            onClick={onClose}
            disabled={isPending}
            className="text-stone-500 hover:text-stone-800 dark:hover:text-stone-200 text-xl leading-none disabled:opacity-50"
          >
            ✕
          </button>
        </div>

        <form className="p-6 space-y-4" onSubmit={onSubmit}>
          <div className="space-y-1">
            <label className="text-sm font-medium text-stone-700 dark:text-stone-300">Date</label>
            <input
              autoFocus
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              required
              disabled={isPending}
              className="w-full border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
            />
            {isTransfer && (
              <p className="text-xs text-stone-500 dark:text-stone-400">
                The date and amount apply to both legs of the transfer.
              </p>
            )}
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium text-stone-700 dark:text-stone-300">Payee</label>
            <input
              value={payee}
              onChange={(e) => setPayee(e.target.value)}
              disabled={isPending}
              className="w-full border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
            />
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium text-stone-700 dark:text-stone-300">
              Category
            </label>
            {isTransfer ? (
              <div className="w-full border border-stone-200 dark:border-stone-700 bg-stone-50 dark:bg-stone-800 rounded-lg px-3 py-2 text-sm text-stone-600 dark:text-stone-400">
                Transfer : {peerAccount?.name ?? "another account"}
              </div>
            ) : (
              <div className="relative">
                <select
                  value={categoryId}
                  onChange={(e) => setCategoryId(e.target.value)}
                  disabled={isPending}
                  className="h-9 w-full appearance-none border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg pl-3 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
                >
                  <option value="">— Unassigned (inflow) —</option>
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>
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
            )}
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium text-stone-700 dark:text-stone-300">Amount</label>
            <input
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              required
              inputMode="decimal"
              placeholder="-12.34"
              disabled={isPending}
              className="w-full border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-2 text-sm text-right tabular-nums focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
            />
            {amountError && (
              <p className="text-sm text-red-600 dark:text-red-400">{amountError}</p>
            )}
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium text-stone-700 dark:text-stone-300">Memo</label>
            <input
              value={memo}
              onChange={(e) => setMemo(e.target.value)}
              disabled={isPending}
              className="w-full border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
            />
          </div>

          {error && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/50 rounded-lg px-3 py-2 text-sm text-red-800 dark:text-red-200">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              disabled={isPending}
              className="border border-stone-300 dark:border-stone-600 text-stone-700 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 rounded-lg px-4 py-2 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isPending}
              className="bg-indigo-600 hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg px-4 py-2 text-sm font-medium"
            >
              {isPending ? "Saving…" : "Save"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
