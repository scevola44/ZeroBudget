import { useEffect, useState } from "react";

import type { Category } from "../api/types";

export type ReassignTarget = { id: number; name: string; groupName: string };

export function DeleteCategoryConfirmModal({
  category,
  /** Categories in the same scope — the only valid destinations. */
  reassignTargets,
  isOpen,
  onClose,
  onConfirm,
  isPending,
  error,
}: {
  category: Category;
  reassignTargets: ReassignTarget[];
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (reassignTo: number | null) => void;
  isPending: boolean;
  error: string | null;
}) {
  const [reassignTo, setReassignTo] = useState("");

  useEffect(() => {
    if (isOpen) setReassignTo("");
  }, [isOpen, category]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-white dark:bg-stone-900 rounded-2xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between px-6 py-4 border-b border-red-200 dark:border-red-900">
          <h2 className="text-lg font-semibold text-red-900 dark:text-red-100">
            Delete category
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

        <div className="p-6 space-y-4">
          <p className="text-sm text-stone-700 dark:text-stone-300">
            Are you sure you want to delete <strong>"{category.name}"</strong>?
          </p>

          <div className="space-y-1">
            <label className="text-sm font-medium text-stone-700 dark:text-stone-300">
              Move its transactions to
            </label>
            <div className="relative">
              <select
                value={reassignTo}
                onChange={(e) => setReassignTo(e.target.value)}
                disabled={isPending || reassignTargets.length === 0}
                className="h-9 w-full appearance-none border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg pl-3 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
              >
                <option value="">— Leave them uncategorized —</option>
                {reassignTargets.map((c) => (
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
          </div>

          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/50 rounded-lg px-3 py-2 text-sm text-red-800 dark:text-red-200">
            Everything assigned to this category is erased along with it, so that money
            returns to Ready to Assign in every month it was budgeted. This cannot be
            undone.
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
              onClick={() => onConfirm(reassignTo ? Number(reassignTo) : null)}
              disabled={isPending}
              className="bg-red-600 hover:bg-red-700 dark:bg-red-700 dark:hover:bg-red-600 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg px-4 py-2 text-sm font-medium"
            >
              {isPending ? "Deleting…" : "Delete"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
