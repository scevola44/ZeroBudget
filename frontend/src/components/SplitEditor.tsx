import { formatCents, parseAmountToCents } from "../lib/money";
import type { CategoryChoice } from "./EditTransactionModal";

export type SplitLineInput = {
  category_id: number | null;
  amountText: string;
  memo: string;
};

export type ParsedSplitLine = {
  category_id: number | null;
  amount_cents: number;
  memo: string;
};

export function emptySplitLine(): SplitLineInput {
  return { category_id: null, amountText: "", memo: "" };
}

/** Parsed split payload for the API, or null if any line's amount is unparseable. */
export function parseSplitLines(lines: SplitLineInput[]): ParsedSplitLine[] | null {
  const parsed: ParsedSplitLine[] = [];
  for (const line of lines) {
    const cents = parseAmountToCents(line.amountText);
    if (cents === null) return null;
    parsed.push({ category_id: line.category_id, amount_cents: cents, memo: line.memo });
  }
  return parsed;
}

/** Amount left to allocate, or null while the total or any line is unparseable. */
export function splitRemainingCents(
  totalAmountText: string,
  lines: SplitLineInput[],
): number | null {
  const total = parseAmountToCents(totalAmountText);
  if (total === null) return null;
  const parsed = parseSplitLines(lines);
  if (parsed === null) return null;
  return total - parsed.reduce((sum, l) => sum + l.amount_cents, 0);
}

/** Expandable split editor, following YNAB's remaining-amount pattern: as
 * lines are added their amounts are subtracted from the parent amount, and
 * the remainder is shown until it reaches zero. */
export function SplitEditor({
  categories,
  totalAmountText,
  lines,
  onChange,
  disabled,
}: {
  categories: CategoryChoice[];
  totalAmountText: string;
  lines: SplitLineInput[];
  onChange: (lines: SplitLineInput[]) => void;
  disabled?: boolean;
}) {
  const remaining = splitRemainingCents(totalAmountText, lines);

  function updateLine(index: number, patch: Partial<SplitLineInput>) {
    onChange(lines.map((l, i) => (i === index ? { ...l, ...patch } : l)));
  }

  return (
    <div className="space-y-2 border border-stone-200 dark:border-stone-700 rounded-lg p-3">
      {lines.map((line, i) => (
        <div key={i} className="flex items-center gap-2">
          <select
            value={line.category_id ?? ""}
            onChange={(e) =>
              updateLine(i, { category_id: e.target.value ? Number(e.target.value) : null })
            }
            disabled={disabled}
            className="h-9 flex-1 min-w-0 appearance-none border border-stone-300 dark:border-stone-600 rounded-lg px-2 text-sm bg-white dark:bg-stone-900 disabled:opacity-50"
          >
            <option value="">— Unassigned —</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.groupName} › {c.name}
              </option>
            ))}
          </select>
          <input
            value={line.memo}
            onChange={(e) => updateLine(i, { memo: e.target.value })}
            placeholder="Memo"
            disabled={disabled}
            className="h-9 w-28 border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-2 text-sm disabled:opacity-50"
          />
          <input
            value={line.amountText}
            onChange={(e) => updateLine(i, { amountText: e.target.value })}
            inputMode="decimal"
            placeholder="-12.34"
            disabled={disabled}
            className="h-9 w-24 border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-2 text-sm text-right tabular-nums disabled:opacity-50"
          />
          <button
            type="button"
            onClick={() => onChange(lines.filter((_, idx) => idx !== i))}
            disabled={disabled}
            title="Remove split line"
            className="text-stone-400 dark:text-stone-500 hover:text-red-600 dark:hover:text-red-400 text-sm px-1 disabled:opacity-50"
          >
            ✕
          </button>
        </div>
      ))}
      <div className="flex items-center justify-between pt-1">
        <button
          type="button"
          onClick={() => onChange([...lines, emptySplitLine()])}
          disabled={disabled}
          className="text-sm text-indigo-600 dark:text-indigo-400 hover:underline disabled:opacity-50"
        >
          + Add split
        </button>
        <span
          className={`text-sm tabular-nums ${
            remaining === 0
              ? "text-stone-500 dark:text-stone-400"
              : "text-red-600 dark:text-red-400"
          }`}
        >
          Remaining: {remaining === null ? "—" : formatCents(remaining)}
        </span>
      </div>
    </div>
  );
}
