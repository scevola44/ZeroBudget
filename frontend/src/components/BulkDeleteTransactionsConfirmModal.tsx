import type { Transaction } from "../api/types";

export function BulkDeleteTransactionsConfirmModal({
  selectedTransactions,
  isOpen,
  onClose,
  onConfirm,
  isPending,
  error,
}: {
  selectedTransactions: Transaction[];
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  isPending: boolean;
  error: string | null;
}) {
  if (!isOpen) return null;

  const selectedIds = new Set(selectedTransactions.map((t) => t.id));
  // A selected transfer leg whose peer isn't also selected still gets
  // cascade-deleted server-side — including peers outside the current
  // date/account/category filters, which this page has no way to count.
  const extraPeerCount = selectedTransactions.filter(
    (t) => t.transfer_peer_id !== null && !selectedIds.has(t.transfer_peer_id),
  ).length;
  const selectedCount = selectedTransactions.length;
  const totalCount = selectedCount + extraPeerCount;

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
            Delete transactions
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
            Are you sure you want to delete{" "}
            <strong>
              {selectedCount} transaction{selectedCount === 1 ? "" : "s"}
            </strong>
            ?
          </p>

          {extraPeerCount > 0 && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/50 rounded-lg px-3 py-2 text-sm text-red-800 dark:text-red-200">
              {extraPeerCount} of these {extraPeerCount === 1 ? "is" : "are"} one leg of a
              transfer. Deleting {extraPeerCount === 1 ? "it" : "them"} also deletes the
              linked transaction on the other side, even if it isn't in your current
              filter — <strong>{totalCount} transactions</strong> will be removed in total.
            </div>
          )}

          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/50 rounded-lg px-3 py-2 text-sm text-red-800 dark:text-red-200">
            This action cannot be undone.
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
              onClick={onConfirm}
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
