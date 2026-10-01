/** Cents of ``totalCents`` not yet accounted for by ``lineCents``. Zero means
 * the split is balanced and ready to submit. */
export function computeSplitRemaining(totalCents: number, lineCents: number[]): number {
  return totalCents - lineCents.reduce((sum, c) => sum + c, 0);
}

/** Whether a set of split lines is ready to submit: balanced, and at least
 * two lines (a single-line "split" is meaningless). */
export function isSplitComplete(totalCents: number, lineCents: number[]): boolean {
  return lineCents.length >= 2 && computeSplitRemaining(totalCents, lineCents) === 0;
}
