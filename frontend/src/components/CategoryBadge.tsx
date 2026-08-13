import type { Transaction } from "../api/types";

type CategoryLike = { name: string };

/** Whether a row is the one "needs attention" state: no category, not a
 * transfer, not Ready to Assign. Mirrors the predicate TransactionsPage uses
 * to filter/count unassigned transactions, so the color accent and the badge
 * always agree with that count. */
export function needsCategory(t: Transaction): boolean {
  return t.category_id === null && t.transfer_peer_id === null && !t.is_ready_to_assign;
}

const pillClass = "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium";

export function CategoryBadge({
  transaction,
  category,
  peerAccountName,
}: {
  transaction: Transaction;
  category: CategoryLike | null;
  /** The other leg's account name, when the transaction is a transfer. */
  peerAccountName?: string;
}) {
  if (transaction.transfer_peer_id !== null) {
    return (
      <span
        className={`${pillClass} bg-violet-100 text-violet-800 dark:bg-violet-900/50 dark:text-violet-200`}
      >
        Transfer : {peerAccountName ?? "another account"}
      </span>
    );
  }

  if (category) {
    return (
      <span
        className={`${pillClass} bg-stone-100 text-stone-700 dark:bg-stone-800 dark:text-stone-300`}
      >
        {category.name}
      </span>
    );
  }

  if (transaction.is_ready_to_assign) {
    return (
      <span
        className={`${pillClass} bg-stone-100 text-stone-500 dark:bg-stone-800 dark:text-stone-400`}
      >
        Ready to Assign
      </span>
    );
  }

  return (
    <span
      className={`${pillClass} bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200`}
    >
      <svg
        className="h-3 w-3 flex-shrink-0"
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
      >
        <rect x="2" y="2" width="12" height="12" rx="2" />
        <path d="M5 8l2 2 4-4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      Category Needed
    </span>
  );
}
