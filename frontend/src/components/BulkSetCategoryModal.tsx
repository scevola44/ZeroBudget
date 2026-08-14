import { useState } from "react";

import type { Transaction } from "../api/types";
import { type CategoryBudgetInfo, type CategoryChoice, CategoryPicker } from "./CategoryPicker";

export function BulkSetCategoryModal({
  selectedTransactions,
  categories,
  budgetByCategoryId,
  isOpen,
  onClose,
  onConfirm,
  isPending,
  error,
}: {
  selectedTransactions: Transaction[];
  /** Every category across every scope — the backend, not this picker, is
   * what enforces scope match, since a bulk selection can span scopes. */
  categories: CategoryChoice[];
  budgetByCategoryId?: Map<number, CategoryBudgetInfo>;
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (categoryId: number | null) => void;
  isPending: boolean;
  error: string | null;
}) {
  const [categoryValue, setCategoryValue] = useState("");

  if (!isOpen) return null;

  const selectedCount = selectedTransactions.length;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-white dark:bg-stone-900 rounded-2xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between px-6 py-4 border-b border-stone-200 dark:border-stone-700">
          <h2 className="text-lg font-semibold">Set category</h2>
          <button
            type="button"
            onClick={onClose}
            disabled={isPending}
            className="text-stone-500 hover:text-stone-800 dark:hover:text-stone-200 text-xl leading-none disabled:opacity-50"
          >
            ✕
          </button>
        </div>

        <div className="p-6 space-y-4">
          <p className="text-sm text-stone-700 dark:text-stone-300">
            Sets the category on{" "}
            <strong>
              {selectedCount} transaction{selectedCount === 1 ? "" : "s"}
            </strong>
            . Transfer legs, split transactions, and rows outside the category's scope are
            left as they are.
          </p>

          <div className="space-y-1">
            <label className="text-sm font-medium text-stone-700 dark:text-stone-300">
              Category
            </label>
            <CategoryPicker
              value={categoryValue}
              onChange={setCategoryValue}
              categories={categories}
              budgetByCategoryId={budgetByCategoryId}
              showReadyToAssignOption={false}
              unassignedLabel="— Unassigned —"
              disabled={isPending}
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
              type="button"
              onClick={() => onConfirm(categoryValue === "" ? null : Number(categoryValue))}
              disabled={isPending}
              className="bg-indigo-600 hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg px-4 py-2 text-sm font-medium"
            >
              {isPending ? "Setting…" : "Set category"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
