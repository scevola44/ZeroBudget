import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import type { Account, Transaction } from "../api/types";
import { type CategoryBudgetInfo, CategoryPicker, type CategoryChoice } from "./CategoryPicker";
import { parseAmountToCents } from "../lib/money";
import { categorySelectValue, parseCategorySelectValue } from "../lib/readyToAssignOption";
import { isSplitComplete } from "../lib/splitRemaining";
import { transferTargetId } from "../lib/transferOption";
import { useDebouncedValue } from "../lib/useDebouncedValue";
import { PayeeAutocomplete } from "./PayeeAutocomplete";
import {
  blankSplitLine,
  SplitEditor,
  type SplitLineDraft,
  type TransactionSplitPayload,
} from "./SplitEditor";

export type TransactionEdit = {
  date: string;
  payee: string;
  memo: string;
  amount_cents: number;
  category_id: number | null;
  is_ready_to_assign: boolean;
  splits: TransactionSplitPayload[];
};

export function EditTransactionModal({
  transaction,
  categories,
  budgetByCategoryId,
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
  /** Current month's assigned/balance per category id, for the remaining-budget pill. */
  budgetByCategoryId?: Map<number, CategoryBudgetInfo>;
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
  const [splitLines, setSplitLines] = useState<SplitLineDraft[] | null>(null);
  const isSplitting = splitLines !== null;

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
    setSplitLines(
      transaction.splits.length > 0
        ? transaction.splits.map((s) => ({
            categoryId: s.category_id === null ? "" : String(s.category_id),
            amount: (s.amount_cents / 100).toFixed(2),
            memo: s.memo,
          }))
        : null,
    );
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

    if (isSplitting) {
      const lineCents = splitLines.map((l) => parseAmountToCents(l.amount));
      if (lineCents.some((c) => c === null) || !isSplitComplete(cents, lineCents as number[])) {
        setAmountError("Split amounts must sum to the transaction amount.");
        return;
      }
      setAmountError(null);
      onSave({
        date,
        payee,
        memo,
        amount_cents: cents,
        category_id: null,
        is_ready_to_assign: false,
        splits: splitLines.map((line, i) => ({
          category_id: line.categoryId === "" ? null : Number(line.categoryId),
          amount_cents: lineCents[i] as number,
          memo: line.memo,
        })),
      });
      return;
    }

    setAmountError(null);
    onSave({
      date,
      payee,
      memo,
      amount_cents: cents,
      ...parseCategorySelectValue(categoryId),
      splits: [],
    });
  }

  // Seeds line 1 from whatever's picked so far; a blank line 2 is where the
  // user starts typing the split. Dropping back to one line (or none) exits
  // split mode, carrying that line's category/amount back to the plain fields.
  function startSplitting() {
    setSplitLines([{ categoryId, amount, memo: "" }, blankSplitLine()]);
  }

  function onSplitLinesChange(lines: SplitLineDraft[]) {
    if (lines.length >= 2) {
      setSplitLines(lines);
      return;
    }
    const [only] = lines;
    setSplitLines(null);
    if (only) {
      setCategoryTouched(true);
      setCategoryId(only.categoryId);
      if (only.amount) setAmount(only.amount);
    }
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
            <PayeeAutocomplete
              value={payee}
              onChange={setPayee}
              disabled={isPending}
              autoFocus
            />
          </div>

          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium text-stone-700 dark:text-stone-300">
                Category
              </label>
              {!isTransfer && !isSplitting && (
                <button
                  type="button"
                  onClick={startSplitting}
                  disabled={isPending}
                  className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline disabled:opacity-50"
                >
                  Split
                </button>
              )}
            </div>
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
            ) : isSplitting ? (
              <SplitEditor
                totalAmountCents={parseAmountToCents(amount)}
                lines={splitLines}
                onChange={onSplitLinesChange}
                categories={categories}
                budgetByCategoryId={budgetByCategoryId}
                disabled={isPending}
              />
            ) : (
              <CategoryPicker
                value={categoryId}
                onChange={(newValue) => {
                  const targetAccountId = transferTargetId(newValue);
                  if (targetAccountId !== null) {
                    onPickTransferTarget?.(targetAccountId);
                    return;
                  }
                  setCategoryTouched(true);
                  setCategoryId(newValue);
                }}
                categories={categories}
                suggestedCategoryIds={suggestedCategoryIds}
                budgetByCategoryId={budgetByCategoryId}
                transferTargets={transferTargets}
                disabled={isPending}
              />
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
