/** A small clickable indicator for Transaction.cleared, YNAB-style: a filled
 * check when the user has reviewed the row, an empty ring when they haven't.
 * Toggles on click without requiring the edit modal — shared by the desktop
 * table and MobileTransactionRow so the control's look and behavior can't
 * drift between them. */
export function ClearedToggle({
  cleared,
  onToggle,
  disabled,
}: {
  cleared: boolean;
  onToggle: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onToggle();
      }}
      disabled={disabled}
      title={cleared ? "Cleared — click to mark as needing review" : "Needs review — click to mark cleared"}
      aria-label={cleared ? "Mark as needing review" : "Mark as cleared"}
      aria-pressed={cleared}
      className={`inline-flex items-center justify-center h-5 w-5 rounded-full border disabled:opacity-50 disabled:cursor-not-allowed transition-colors ${
        cleared
          ? "bg-emerald-100 border-emerald-300 text-emerald-700 dark:bg-emerald-900/50 dark:border-emerald-700 dark:text-emerald-300"
          : "bg-transparent border-stone-300 text-transparent hover:border-stone-400 dark:border-stone-600 dark:hover:border-stone-500"
      }`}
    >
      <svg className="h-3 w-3" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M4 8l3 3 5-6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  );
}
