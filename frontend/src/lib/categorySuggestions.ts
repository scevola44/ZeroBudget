/** Split ``categories`` into the ones ``suggestedIds`` names (in that rank order) and the rest, unchanged. */
export function partitionSuggested<T extends { id: number }>(
  categories: T[],
  suggestedIds: number[],
): { suggested: T[]; rest: T[] } {
  const byId = new Map(categories.map((c) => [c.id, c]));
  const suggested = suggestedIds
    .map((id) => byId.get(id))
    .filter((c): c is T => c !== undefined);
  const suggestedIdSet = new Set(suggested.map((c) => c.id));
  const rest = categories.filter((c) => !suggestedIdSet.has(c.id));
  return { suggested, rest };
}
