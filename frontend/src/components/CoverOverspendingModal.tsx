import { useEffect, useState } from "react";

import { formatCents, parseAmountToCents } from "../lib/money";

export type CoverOverspendingTarget = { id: number; name: string; balanceCents: number };
export type CoverSourceCandidate = { id: number; name: string; groupName: string; balanceCents: number };

export function CoverOverspendingModal({
  targetCategory,
  sourceCandidates,
  isOpen,
  onClose,
  onConfirm,
  isPending,
  error,
}: {
  targetCategory: CoverOverspendingTarget | null;
  sourceCandidates: CoverSourceCandidate[];
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (sourceCategoryId: number, amountCents: number) => void;
  isPending: boolean;
  error: string | null;
}) {
  const [sourceCategoryId, setSourceCategoryId] = useState("");
  const [amountDraft, setAmountDraft] = useState("");

  useEffect(() => {
    if (isOpen) {
      setSourceCategoryId("");
      setAmountDraft("");
    }
  }, [isOpen, targetCategory]);

  if (!isOpen || !targetCategory) return null;

  const shortfallCents = -targetCategory.balanceCents;

  function selectSource(value: string) {
    setSourceCategoryId(value);
    const source = sourceCandidates.find((c) => String(c.id) === value);
    if (source) {
      const suggestedCents = Math.min(shortfallCents, source.balanceCents);
      setAmountDraft((suggestedCents / 100).toFixed(2));
    } else {
      setAmountDraft("");
    }
  }

  const parsedAmountCents = parseAmountToCents(amountDraft);
  const canConfirm =
    !isPending &&
    sourceCategoryId !== "" &&
    parsedAmountCents !== null &&
    parsedAmountCents > 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-white dark:bg-stone-900 rounded-2xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between px-6 py-4 border-b border-stone-200 dark:border-stone-700">
          <h2 className="text-lg font-semibold text-stone-900 dark:text-stone-100">
            Cover overspending
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
            <strong>{targetCategory.name}</strong> is {formatCents(shortfallCents)} over budget.
          </p>

          <div className="space-y-1">
            <label className="text-sm font-medium text-stone-700 dark:text-stone-300">
              Move money from
            </label>
            <div className="relative">
              <select
                value={sourceCategoryId}
                onChange={(e) => selectSource(e.target.value)}
                disabled={isPending || sourceCandidates.length === 0}
                className="h-9 w-full appearance-none border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg pl-3 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
              >
                <option value="">
                  {sourceCandidates.length === 0
                    ? "— No categories with available funds —"
                    : "— Select a category —"}
                </option>
                {sourceCandidates.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.groupName} › {c.name} — {formatCents(c.balanceCents)} available
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

          <div className="space-y-1">
            <label className="text-sm font-medium text-stone-700 dark:text-stone-300">
              Amount to move
            </label>
            <input
              value={amountDraft}
              onChange={(e) => setAmountDraft(e.target.value)}
              disabled={isPending || sourceCategoryId === ""}
              inputMode="decimal"
              className="h-9 w-full border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
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
              onClick={() => {
                if (parsedAmountCents !== null) {
                  onConfirm(Number(sourceCategoryId), parsedAmountCents);
                }
              }}
              disabled={!canConfirm}
              className="bg-indigo-600 hover:bg-indigo-700 dark:bg-indigo-700 dark:hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg px-4 py-2 text-sm font-medium"
            >
              {isPending ? "Moving…" : "Move Money"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
