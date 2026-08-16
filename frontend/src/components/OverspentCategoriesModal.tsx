import { availablePillClass } from "../lib/budgetAvailability";
import { formatCents } from "../lib/money";

export type OverspentCategoryRow = {
  id: number;
  name: string;
  groupName: string;
  assignedCents: number;
  balanceCents: number; // always < 0 in this list
};

export function OverspentCategoriesModal({
  scopeName,
  categories,
  isOpen,
  onClose,
  onSelectCategory,
}: {
  scopeName: string;
  categories: OverspentCategoryRow[];
  isOpen: boolean;
  onClose: () => void;
  onSelectCategory: (categoryId: number) => void;
}) {
  if (!isOpen) return null;

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
            Overspent categories — {scopeName}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-stone-500 hover:text-stone-800 dark:hover:text-stone-200 text-xl leading-none"
          >
            ✕
          </button>
        </div>

        <div className="p-6 space-y-4">
          {categories.length === 0 ? (
            <div className="bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-900/50 rounded-lg px-3 py-2 text-sm text-emerald-800 dark:text-emerald-200">
              Nothing overspent in {scopeName} right now.
            </div>
          ) : (
            <div className="space-y-1">
              <p className="text-sm text-stone-600 dark:text-stone-400">
                Select a category to cover its overspending.
              </p>
              {categories.map((cat) => (
                <button
                  key={cat.id}
                  type="button"
                  onClick={() => onSelectCategory(cat.id)}
                  className="w-full flex items-center justify-between gap-3 px-3 py-2 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-800 text-sm text-left"
                >
                  <span className="truncate text-stone-700 dark:text-stone-300">
                    {cat.groupName} › {cat.name}
                  </span>
                  <span
                    className={`shrink-0 inline-block px-2.5 py-1 rounded-full text-xs font-semibold tabular-nums ${availablePillClass(cat.assignedCents, cat.balanceCents)}`}
                  >
                    {formatCents(cat.balanceCents)}
                  </span>
                </button>
              ))}
            </div>
          )}

          <div className="flex justify-end pt-4">
            <button
              type="button"
              onClick={onClose}
              className="border border-stone-300 dark:border-stone-600 text-stone-700 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 rounded-lg px-4 py-2 text-sm"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
