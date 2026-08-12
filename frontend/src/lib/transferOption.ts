// Marks a "Transfer : <account>" choice in a category picker, YNAB-style.
// Shared by AccountDetailPage, TransactionsPage, and EditTransactionModal so
// the encoding can't drift between them.
export const TRANSFER_OPTION_PREFIX = "transfer:";

export function transferTargetId(categoryChoice: string): number | null {
  if (!categoryChoice.startsWith(TRANSFER_OPTION_PREFIX)) return null;
  return Number(categoryChoice.slice(TRANSFER_OPTION_PREFIX.length));
}
