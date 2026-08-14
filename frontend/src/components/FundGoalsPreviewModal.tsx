import type { FundGoalsPreview } from "../api/types";
import { formatCents } from "../lib/money";

export function FundGoalsPreviewModal({
  scopeName,
  preview,
  isLoading,
  isOpen,
  onClose,
  onConfirm,
  isPending,
  error,
}: {
  scopeName: string;
  preview: FundGoalsPreview | null;
  isLoading: boolean;
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  isPending: boolean;
  error: string | null;
}) {
  if (!isOpen) return null;

  const entries = preview?.entries ?? [];

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
            Fund goals — {scopeName}
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
          {isLoading && (
            <div className="text-sm text-stone-500 dark:text-stone-400">Loading preview…</div>
          )}

          {!isLoading && preview && entries.length === 0 && (
            <div className="bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-900/50 rounded-lg px-3 py-2 text-sm text-emerald-800 dark:text-emerald-200">
              Nothing to fund — every category is on track.
            </div>
          )}

          {!isLoading && preview && entries.length > 0 && (
            <div className="space-y-2">
              {entries.map((entry) => {
                const capped = entry.amount_cents < entry.needed_cents;
                return (
                  <div
                    key={entry.category_id}
                    className="flex items-center justify-between text-sm"
                  >
                    <span className="text-stone-700 dark:text-stone-300">
                      {entry.category_name}
                    </span>
                    <span className="text-right tabular-nums">
                      <span
                        className={
                          capped
                            ? "text-amber-700 dark:text-amber-400 font-semibold"
                            : "text-stone-900 dark:text-stone-100 font-semibold"
                        }
                      >
                        {formatCents(entry.amount_cents)}
                      </span>
                      <span className="text-stone-400 dark:text-stone-500">
                        {" "}
                        of {formatCents(entry.needed_cents)}
                      </span>
                    </span>
                  </div>
                );
              })}

              <div className="flex items-center justify-between text-sm font-semibold pt-2 border-t border-stone-200 dark:border-stone-700">
                <span>Total</span>
                <span className="tabular-nums">
                  {formatCents(preview.total_amount_cents)} of{" "}
                  {formatCents(preview.ready_to_assign_cents)} ready to assign
                </span>
              </div>

              {entries.some((e) => e.amount_cents < e.needed_cents) && (
                <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-900/50 rounded-lg px-3 py-2 text-sm text-amber-800 dark:text-amber-200">
                  Ready to Assign doesn't cover everything — categories are funded in order
                  shown, and the rest are left for next time.
                </div>
              )}
            </div>
          )}

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
              onClick={onConfirm}
              disabled={isPending || isLoading || entries.length === 0}
              className="bg-indigo-600 hover:bg-indigo-700 dark:bg-indigo-700 dark:hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg px-4 py-2 text-sm font-medium"
            >
              {isPending ? "Funding…" : "Fund goals"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
