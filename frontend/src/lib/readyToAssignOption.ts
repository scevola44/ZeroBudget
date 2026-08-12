// Marks a "Ready to Assign" choice in a category picker, YNAB-style: the
// transaction stays uncategorized but is flagged as deliberately so. Shared
// by AccountDetailPage, TransactionsPage, and EditTransactionModal so the
// encoding can't drift between them.
export const READY_TO_ASSIGN_OPTION_VALUE = "ready-to-assign";

export function categorySelectValue(
  categoryId: number | null,
  isReadyToAssign: boolean,
): string {
  if (isReadyToAssign) return READY_TO_ASSIGN_OPTION_VALUE;
  return categoryId === null ? "" : String(categoryId);
}

export function parseCategorySelectValue(
  value: string,
): { category_id: number | null; is_ready_to_assign: boolean } {
  if (value === READY_TO_ASSIGN_OPTION_VALUE) {
    return { category_id: null, is_ready_to_assign: true };
  }
  return { category_id: value === "" ? null : Number(value), is_ready_to_assign: false };
}
