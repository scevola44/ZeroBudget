import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import type { Account } from "../api/types";
import { parseAmountToCents } from "../lib/money";
import { todayISO } from "../lib/dates";
import { parseCategorySelectValue } from "../lib/readyToAssignOption";
import { useDebouncedValue } from "../lib/useDebouncedValue";
import { type CategoryBudgetInfo, type CategoryChoice, CategoryPicker } from "./CategoryPicker";

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
  budgetByCategoryId,
  isOpen,
  onClose,
  onSave,
  isPending,
  error,
}: {
  accounts: Account[];
  /** All categories, flat — filtered to the chosen account's scope on each render. */
  categoriesByScope: (CategoryChoice & { groupScope: string })[];
  /** Current month's assigned/balance per category id, for the remaining-budget pill. */
  budgetByCategoryId?: Map<number, CategoryBudgetInfo>;
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
  // Whether the user has picked a category themselves this entry, so a
  // suggestion arriving afterward never overrides that choice.
  const [categoryTouched, setCategoryTouched] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setAccountId(openAccounts[0] ? String(openAccounts[0].id) : "");
    setDate(todayISO());
    setPayee("");
    setMemo("");
    setAmount("");
    setCategoryId("");
    setCategoryTouched(false);
    setAmountError(null);
    // openAccounts is derived from `accounts` each render; only re-seed when the modal opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  const selectedAccount = openAccounts.find((a) => String(a.id) === accountId);
  const categories = selectedAccount
    ? categoriesByScope.filter((c) => c.groupScope === selectedAccount.scope)
    : [];

  const debouncedPayee = useDebouncedValue(payee, 300);
  const suggestionsQuery = useQuery<number[]>({
    queryKey: ["category-suggestions", selectedAccount?.id, debouncedPayee],
    queryFn: () =>
      api<number[]>(
        `/api/transactions/category-suggestions?account_id=${selectedAccount?.id}&payee=${encodeURIComponent(debouncedPayee)}`,
      ),
    enabled: isOpen && selectedAccount !== undefined && debouncedPayee.trim().length > 0,
  });
  const suggestedCategoryIds = suggestionsQuery.data ?? [];

  // Tracks the top suggestion into the field as the payee changes, but stops
  // the moment the user picks a category themselves.
  useEffect(() => {
    if (categoryTouched) return;
    setCategoryId(suggestedCategoryIds.length > 0 ? String(suggestedCategoryIds[0]) : "");
  }, [suggestedCategoryIds, categoryTouched]);

  if (!isOpen) return null;

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
                setCategoryTouched(false);
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
            <CategoryPicker
              value={categoryId}
              onChange={(newValue) => {
                setCategoryTouched(true);
                setCategoryId(newValue);
              }}
              categories={categories}
              suggestedCategoryIds={suggestedCategoryIds}
              budgetByCategoryId={budgetByCategoryId}
              disabled={isPending}
            />
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
