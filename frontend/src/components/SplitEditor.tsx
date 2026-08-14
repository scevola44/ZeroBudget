import { formatCents, parseAmountToCents } from "../lib/money";
import { computeSplitRemaining } from "../lib/splitRemaining";
import { type CategoryBudgetInfo, type CategoryChoice, CategoryPicker } from "./CategoryPicker";

export type SplitLineDraft = {
  categoryId: string; // CategoryPicker value convention: "" = unassigned
  amount: string; // raw text, parsed via parseAmountToCents
  memo: string;
};

/** The shape a split line takes in a transaction create/update request body. */
export type TransactionSplitPayload = {
  category_id: number | null;
  amount_cents: number;
  memo: string;
};

export function blankSplitLine(): SplitLineDraft {
  return { categoryId: "", amount: "", memo: "" };
}

/**
 * Category/amount/memo lines for a split transaction, with a live remaining
 * indicator. Swaps in for CategoryPicker in the transaction form once split
 * mode is active — same role the transfer read-only block already plays in
 * EditTransactionModal.
 */
export function SplitEditor({
  totalAmountCents,
  lines,
  onChange,
  categories,
  budgetByCategoryId,
  disabled,
}: {
  /** Null while the transaction's own amount field isn't a valid number yet. */
  totalAmountCents: number | null;
  lines: SplitLineDraft[];
  onChange: (lines: SplitLineDraft[]) => void;
  /** Already narrowed to the transaction's account scope by the caller. */
  categories: CategoryChoice[];
  budgetByCategoryId?: Map<number, CategoryBudgetInfo>;
  disabled?: boolean;
}) {
  const lineCents = lines.map((l) => parseAmountToCents(l.amount) ?? 0);
  const remaining =
    totalAmountCents === null ? null : computeSplitRemaining(totalAmountCents, lineCents);

  function updateLine(index: number, patch: Partial<SplitLineDraft>) {
    onChange(lines.map((line, i) => (i === index ? { ...line, ...patch } : line)));
  }

  function removeLine(index: number) {
    onChange(lines.filter((_, i) => i !== index));
  }

  return (
    <div className="space-y-3">
      {lines.map((line, index) => (
        <div
          key={index}
          className="space-y-1.5 border border-stone-200 dark:border-stone-700 rounded-lg p-2"
        >
          <div className="flex gap-2 items-start">
            <div className="flex-1">
              <CategoryPicker
                value={line.categoryId}
                onChange={(v) => updateLine(index, { categoryId: v })}
                categories={categories}
                budgetByCategoryId={budgetByCategoryId}
                showReadyToAssignOption={false}
                disabled={disabled}
              />
            </div>
            <input
              value={line.amount}
              onChange={(e) => updateLine(index, { amount: e.target.value })}
              inputMode="decimal"
              placeholder="-12.34"
              disabled={disabled}
              className="w-28 border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-2 text-sm text-right tabular-nums focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
            />
            <button
              type="button"
              onClick={() => removeLine(index)}
              disabled={disabled}
              title="Remove split line"
              className="text-stone-400 hover:text-red-600 dark:hover:text-red-400 px-1 py-2 disabled:opacity-50"
            >
              ✕
            </button>
          </div>
          <input
            value={line.memo}
            onChange={(e) => updateLine(index, { memo: e.target.value })}
            placeholder="Memo (optional)"
            disabled={disabled}
            className="w-full border border-stone-200 dark:border-stone-700 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-1.5 text-xs text-stone-600 dark:text-stone-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
          />
        </div>
      ))}

      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => onChange([...lines, blankSplitLine()])}
          disabled={disabled}
          className="text-sm text-indigo-600 dark:text-indigo-400 hover:underline disabled:opacity-50"
        >
          + Add split
        </button>
        {remaining !== null && (
          <span
            className={`text-sm font-medium tabular-nums ${
              remaining === 0
                ? "text-emerald-700 dark:text-emerald-400"
                : "text-amber-700 dark:text-amber-400"
            }`}
          >
            Remaining: {formatCents(remaining)}
          </span>
        )}
      </div>
    </div>
  );
}
