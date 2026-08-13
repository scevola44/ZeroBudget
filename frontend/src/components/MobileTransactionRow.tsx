import type { Account, Transaction } from "../api/types";
import { formatCents } from "../lib/money";
import { CategoryBadge, needsCategory } from "./CategoryBadge";

export function MobileTransactionRow({
  transaction,
  account,
  category,
  peerAccountName,
  selectionMode,
  selected,
  onToggleSelect,
  onOpen,
}: {
  transaction: Transaction;
  account: Account | undefined;
  category: { name: string } | null;
  peerAccountName?: string;
  selectionMode: boolean;
  selected: boolean;
  onToggleSelect: () => void;
  onOpen: () => void;
}) {
  const accentClass = needsCategory(transaction)
    ? "border-amber-400 dark:border-amber-600"
    : "border-indigo-200 dark:border-indigo-800";

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={selectionMode ? onToggleSelect : onOpen}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          selectionMode ? onToggleSelect() : onOpen();
        }
      }}
      className={`flex items-start gap-3 px-4 py-3 border-l-4 ${accentClass} border-b border-stone-100 dark:border-stone-800 last:border-b-0 hover:bg-stone-50 dark:hover:bg-stone-800/50 cursor-pointer`}
    >
      {selectionMode && (
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggleSelect}
          onClick={(e) => e.stopPropagation()}
          aria-label={`Select transaction on ${transaction.date}`}
          className="mt-1 rounded accent-indigo-600"
        />
      )}
      <div className="flex-1 min-w-0 space-y-1">
        <div className="flex items-baseline justify-between gap-3">
          <span className="font-medium truncate">
            {transaction.payee || <span className="text-stone-400 dark:text-stone-500">—</span>}
          </span>
          <span
            className={`tabular-nums font-semibold whitespace-nowrap ${
              transaction.amount_cents >= 0
                ? "text-emerald-700 dark:text-emerald-400"
                : "text-stone-900 dark:text-stone-100"
            }`}
          >
            {formatCents(transaction.amount_cents)}
          </span>
        </div>
        <div className="flex items-center justify-between gap-3">
          <CategoryBadge
            transaction={transaction}
            category={category}
            peerAccountName={peerAccountName}
          />
          <span className="text-xs text-stone-500 dark:text-stone-400 truncate">
            {account?.name ?? "—"}
          </span>
        </div>
      </div>
    </div>
  );
}
