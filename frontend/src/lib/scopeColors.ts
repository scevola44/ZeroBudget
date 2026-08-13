// Colours for scopes, indexed by a scope's `sort_order`.
//
// Kept separate from `chartColors.ts` on purpose: that palette's hue order was
// validated for categorical chart series, and slots 0 and 1 there are not the
// sky/violet that Personal and Family have always rendered in. Reusing it would
// repaint every existing user's chips on upgrade.
//
// Tailwind's scanner only emits CSS for classes it can find literally in the
// source, so a name built by interpolation (`bg-${hue}-100`) silently produces
// no CSS and an invisible chip. Every entry here is a complete class string.
// Never interpolate these.
//
// Indexing by the `sort_order` *value* rather than by position in the fetched
// list is what keeps colours stable: deleting a scope leaves a gap, and the
// survivors keep the colours the user already knows them by.

export const SCOPE_CHIP_CLASSES = [
  "bg-sky-100 text-sky-800 dark:bg-sky-900/50 dark:text-sky-200",
  "bg-violet-100 text-violet-800 dark:bg-violet-900/50 dark:text-violet-200",
  "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-200",
  "bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200",
  "bg-rose-100 text-rose-800 dark:bg-rose-900/50 dark:text-rose-200",
  "bg-teal-100 text-teal-800 dark:bg-teal-900/50 dark:text-teal-200",
] as const;

// Solid fills for the Insights split bar, one per slot above.
export const SCOPE_BAR_CLASSES = [
  "bg-sky-600",
  "bg-violet-600 dark:bg-violet-500",
  "bg-emerald-600",
  "bg-amber-500 dark:bg-amber-600",
  "bg-rose-500",
  "bg-teal-600",
] as const;

/** How many scopes get their own colour before the palette repeats. */
export const SCOPE_PALETTE_SIZE = SCOPE_CHIP_CLASSES.length;

function paletteSlot(sortOrder: number): number {
  // sort_order is server-assigned and non-negative, but a wrap keeps this total
  // for any input rather than returning undefined off the end.
  return ((sortOrder % SCOPE_PALETTE_SIZE) + SCOPE_PALETTE_SIZE) % SCOPE_PALETTE_SIZE;
}

export function scopeChipClass(sortOrder: number): string {
  return SCOPE_CHIP_CLASSES[paletteSlot(sortOrder)];
}

export function scopeBarClass(sortOrder: number): string {
  return SCOPE_BAR_CLASSES[paletteSlot(sortOrder)];
}
