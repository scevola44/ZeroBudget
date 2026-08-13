import { useEffect, useState } from "react";

import type { Account } from "../api/types";
import { parseAmountToCents } from "../lib/money";
import { todayISO } from "../lib/dates";
import {
  READY_TO_ASSIGN_OPTION_VALUE,
  parseCategorySelectValue,
} from "../lib/readyToAssignOption";
import type { CategoryChoice } from "./EditTransactionModal";

export type TransactionCreateInput = {
  account_id: number;
  date: string;
  payee: string;
  memo: string;
  amount_cents: number;
  category_id: number | null;
  is_ready_to_assign: boolean;
};

export function AddTransactionModal({
  accounts,
  categoriesByScope,
  isOpen,
  onClose,
  onSave,
  isPending,
  error,
}: {
  accounts: Account[];
  /** All categories, flat — filtered to the chosen account's scope on each render. */
  categoriesByScope: (CategoryChoice & { groupScope: string })[];
  isOpen: boolean;
  onClose: () => void;
  onSave: (input: TransactionCreateInput) => void;
  isPending: boolean;
  error: string | null;
}) {
  const openAccounts = accounts.filter((a) => !a.closed);
  const [accountId, setAccountId] = useState<string>("");
  const [date, setDate] = useState(todayISO());
  const [payee, setPayee] = useState("");
  const [memo, setMemo] = useState("");
  const [amount, setAmount] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [amountError, setAmountError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    setAccountId(openAccounts[0] ? String(openAccounts[0].id) : "");
    setDate(todayISO());
    setPayee("");
    setMemo("");
    setAmount("");
    setCategoryId("");
    setAmountError(null);
    // openAccounts is derived from `accounts` each render; only re-seed when the modal opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  if (!isOpen) return null;

  const selectedAccount = openAccounts.find((a) => String(a.id) === accountId);
  const categories = selectedAccount
    ? categoriesByScope.filter((c) => c.groupScope === selectedAccount.scope)
    : [];

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedAccount) return;
    const cents = parseAmountToCents(amount);
    if (cents === null) {
      setAmountError("Enter a valid amount (use '-' for outflow).");
      return;
    }
    setAmountError(null);
    onSave({
      account_id: selectedAccount.id,
      date,
      payee,
      memo,
      amount_cents: cents,
      ...parseCategorySelectValue(categoryId),
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
          <h2 className="text-lg font-semibold">Add transaction</h2>
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
            <label className="text-sm font-medium text-stone-700 dark:text-stone-300">
              Account
            </label>
            <select
              value={accountId}
              onChange={(e) => {
                setAccountId(e.target.value);
                setCategoryId("");
              }}
              required
              disabled={isPending}
              className="h-9 w-full appearance-none border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
            >
              {openAccounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium text-stone-700 dark:text-stone-300">Date</label>
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              required
              disabled={isPending}
              className="w-full border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
            />
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
            <select
              value={categoryId}
              onChange={(e) => setCategoryId(e.target.value)}
              disabled={isPending}
              className="h-9 w-full appearance-none border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
            >
              <option value="">— Unassigned (inflow) —</option>
              <option value={READY_TO_ASSIGN_OPTION_VALUE}>Ready to Assign</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.groupName} › {c.name}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium text-stone-700 dark:text-stone-300">
              Amount
            </label>
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
              disabled={isPending || !selectedAccount}
              className="bg-indigo-600 hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg px-4 py-2 text-sm font-medium"
            >
              {isPending ? "Adding…" : "Add"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
