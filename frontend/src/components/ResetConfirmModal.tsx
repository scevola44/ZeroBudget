import type { ResetOption } from "@zerobudget/core";
import { useEffect, useState } from "react";

import { useCountdown } from "../lib/useCountdown";

const CONFIRM_DELAY_SECONDS = 5;

// Adding a reset option means adding one entry here (and one backend handler).
const RESET_OPTIONS: { value: ResetOption; label: string; description: string }[] = [
  {
    value: "transactions",
    label: "Transactions",
    description:
      "Deletes every transaction on every account, so all balances drop to 0. Linked accounts re-align to the real bank balance on the next sync, but only the current month's transactions come back. Manual accounts stay at 0 until you set their balance.",
  },
  {
    value: "assignments",
    label: "Assignments",
    description:
      "Removes every amount assigned to a category, in past, present and future months. Categories and their goals are kept.",
  },
];

const WARNING_BOX_CLASS =
  "bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/50 rounded-lg px-3 py-2 text-sm text-red-800 dark:text-red-200";

export function ResetConfirmModal({
  isOpen,
  onClose,
  onConfirm,
  isPending,
  error,
}: {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (options: ResetOption[]) => void;
  isPending: boolean;
  error: string | null;
}) {
  const [selected, setSelected] = useState<Set<ResetOption>>(new Set());
  const secondsLeft = useCountdown(CONFIRM_DELAY_SECONDS, isOpen);

  useEffect(() => {
    if (isOpen) setSelected(new Set());
  }, [isOpen]);

  if (!isOpen) return null;

  const toggle = (option: ResetOption) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(option)) next.delete(option);
      else next.add(option);
      return next;
    });

  const isConfirmLocked = secondsLeft > 0 || selected.size === 0 || isPending;
  const confirmLabel = isPending
    ? "Resetting…"
    : secondsLeft > 0
      ? `Reset (${secondsLeft})`
      : "Reset";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isPending) onClose();
      }}
    >
      <div className="bg-white dark:bg-stone-900 rounded-2xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between px-6 py-4 border-b border-red-200 dark:border-red-900">
          <h2 className="text-lg font-semibold text-red-900 dark:text-red-100">Reset data</h2>
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
            Choose what to reset. Accounts, bank connections, categories and goals are always kept.
          </p>

          <ul className="space-y-3">
            {RESET_OPTIONS.map((option) => (
              <li key={option.value}>
                <label className="flex gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selected.has(option.value)}
                    onChange={() => toggle(option.value)}
                    disabled={isPending}
                    className="mt-1"
                  />
                  <span>
                    <span className="block text-sm font-medium">{option.label}</span>
                    <span className="block text-sm text-stone-600 dark:text-stone-400">
                      {option.description}
                    </span>
                  </span>
                </label>
              </li>
            ))}
          </ul>

          <div className={WARNING_BOX_CLASS}>This action cannot be undone.</div>

          {error && <div className={WARNING_BOX_CLASS}>{error}</div>}

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
              onClick={() => onConfirm([...selected])}
              disabled={isConfirmLocked}
              className="bg-red-600 hover:bg-red-700 dark:bg-red-700 dark:hover:bg-red-600 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg px-4 py-2 text-sm font-medium"
            >
              {confirmLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
