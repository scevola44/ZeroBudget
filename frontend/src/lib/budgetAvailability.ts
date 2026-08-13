// Shared with anywhere that shows a category's remaining budget as a
// color-coded pill (the Budget page's Available column, the transaction
// modals' category picker) so the color rules can't drift between them.
export function availablePillClass(assignedCents: number, balanceCents: number): string {
  if (balanceCents < 0) {
    return "bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-200";
  }
  if (assignedCents === 0) {
    return "bg-stone-200 text-stone-600 dark:bg-stone-800 dark:text-stone-300";
  }
  if (balanceCents >= assignedCents) {
    return "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-200";
  }
  return "bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200";
}
