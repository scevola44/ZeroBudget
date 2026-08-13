import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import type { Account, Transaction } from "../api/types";
import { partitionSuggested } from "../lib/categorySuggestions";
import { parseAmountToCents } from "../lib/money";
import {
  READY_TO_ASSIGN_OPTION_VALUE,
  categorySelectValue,
  parseCategorySelectValue,
} from "../lib/readyToAssignOption";
import { TRANSFER_OPTION_PREFIX, transferTargetId } from "../lib/transferOption";
import { useDebouncedValue } from "../lib/useDebouncedValue";

export type TransactionEdit = {
  date: string;
  payee: string;
  memo: string;
  amount_cents: number;
  category_id: number | null;
  is_ready_to_assign: boolean;
};

export type CategoryChoice = { id: number; name: string; groupName: string };

export function EditTransactionModal({
  transaction,
  categories,
  peerAccount,
  transferTargets,
  isOpen,
  onClose,
  onSave,
  onPickTransferTarget,
  onUnlinkTransfer,
  onDelete,
  isPending,
  isDeletePending,
  error,
}: {
  transaction: Transaction;
  /** Already narrowed to the account's scope by the caller. */
  categories: CategoryChoice[];
  /** The other leg's account, when this transaction is a transfer. */
  peerAccount: Account | null;
  /** Other accounts this (non-transfer) transaction could be turned into a transfer with. */
  transferTargets?: Account[];
  isOpen: boolean;
  onClose: () => void;
  onSave: (edit: TransactionEdit) => void;
  /** Picking "Transfer : <account>" hands off to the link-transfer flow instead of saving here. */
  onPickTransferTarget?: (accountId: number) => void;
  /** Break the pair, keeping both transactions. Only shown for transfer legs. */
  onUnlinkTransfer?: () => void;
  /** Deletes this transaction (both legs, if a transfer). Omit to hide the button. */
  onDelete?: () => void;
  isPending: boolean;
  isDeletePending?: boolean;
  error: string | null;
}) {
  const [date, setDate] = useState(transaction.date);
  const [payee, setPayee] = useState(transaction.payee);
  const [memo, setMemo] = useState(transaction.memo);
  const [amount, setAmount] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [amountError, setAmountError] = useState<string | null>(null);
  // Whether the user has picked a category themselves since opening the
  // modal, so a suggestion arriving afterward never overrides that choice.
  const [categoryTouched, setCategoryTouched] = useState(false);

  const isTransfer = transaction.transfer_peer_id !== null;

  useEffect(() => {
    if (!isOpen) return;
    setDate(transaction.date);
    setPayee(transaction.payee);
    setMemo(transaction.memo);
    setAmount((transaction.amount_cents / 100).toFixed(2));
    setCategoryId(categorySelectValue(transaction.category_id, transaction.is_ready_to_assign));
    setAmountError(null);
    setCategoryTouched(false);
  }, [isOpen, transaction]);

  // Only suggest once the payee is actually edited away from its saved value —
  // the category already on screen reflects a deliberate prior choice.
  const debouncedPayee = useDebouncedValue(payee, 300);
  const suggestionsQuery = useQuery<number[]>({
    queryKey: ["category-suggestions", transaction.account_id, debouncedPayee],
    queryFn: () =>
      api<number[]>(
        `/api/transactions/category-suggestions?account_id=${transaction.account_id}&payee=${encodeURIComponent(debouncedPayee)}`,
      ),
    enabled:
      isOpen &&
      !isTransfer &&
      debouncedPayee.trim().length > 0 &&
      debouncedPayee !== transaction.payee,
  });
  const suggestedCategoryIds = suggestionsQuery.data ?? [];
  const { suggested: suggestedCategories, rest: otherCategories } = partitionSuggested(
    categories,
    suggestedCategoryIds,
  );

  // Leaves the saved category alone until the payee is actually edited away
  // from it; from then on, tracks the top suggestion until the user picks a
  // category themselves.
  useEffect(() => {
    if (categoryTouched || debouncedPayee === transaction.payee) return;
    setCategoryId(suggestedCategoryIds.length > 0 ? String(suggestedCategoryIds[0]) : "");
  }, [suggestedCategoryIds, categoryTouched, debouncedPayee, transaction.payee]);

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
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              required
              disabled={isPending}
              className="w-full border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
            />
            {isTransfer && (
              <p className="text-xs text-stone-500 dark:text-stone-400">
                Each leg keeps its own date; the amount applies to both.
              </p>
            )}
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium text-stone-700 dark:text-stone-300">Payee</label>
            <input
              autoFocus
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
              <div className="w-full border border-stone-200 dark:border-stone-700 bg-stone-50 dark:bg-stone-800 rounded-lg px-3 py-2 text-sm text-stone-600 dark:text-stone-400 flex items-center justify-between gap-3">
                <span>Transfer : {peerAccount?.name ?? "another account"}</span>
                {onUnlinkTransfer && (
                  <button
                    type="button"
                    onClick={onUnlinkTransfer}
                    disabled={isPending}
                    title="Keeps both transactions, just not as a transfer"
                    className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline disabled:opacity-50 whitespace-nowrap"
                  >
                    Unlink
                  </button>
                )}
              </div>
            ) : (
              <div className="relative">
                <select
                  value={categoryId}
                  onChange={(e) => {
                    const targetAccountId = transferTargetId(e.target.value);
                    if (targetAccountId !== null) {
                      onPickTransferTarget?.(targetAccountId);
                      return;
                    }
                    setCategoryTouched(true);
                    setCategoryId(e.target.value);
                  }}
                  disabled={isPending}
                  className="h-9 w-full appearance-none border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg pl-3 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
                >
                  <option value="">— Unassigned (inflow) —</option>
                  <option value={READY_TO_ASSIGN_OPTION_VALUE}>Ready to Assign</option>
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
                  {transferTargets && transferTargets.length > 0 && (
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

          <div className="flex items-center justify-between gap-3 pt-4">
            {onDelete ? (
              <button
                type="button"
                onClick={onDelete}
                disabled={isPending || isDeletePending}
                title={
                  transaction.transfer_peer_id !== null
                    ? "Deletes both legs of the transfer"
                    : undefined
                }
                className="text-sm text-red-600 dark:text-red-400 hover:underline disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isDeletePending ? "Deleting…" : "Delete"}
              </button>
            ) : (
              <span />
            )}
            <div className="flex gap-3">
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
          </div>
        </form>
      </div>
    </div>
  );
}
