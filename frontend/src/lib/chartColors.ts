// A fixed categorical palette for the Insights charts.
//
// Every entry is a complete class-pair string. Tailwind's scanner only emits CSS
// for classes it can find literally in the source, so a name built by
// interpolation (`bg-${hue}-600`) silently produces no CSS and an invisible bar.
// Never interpolate these.
//
// The hue order was validated against the app's real surfaces — white and
// stone-900 — for lightness, chroma, contrast, and colour-vision separation of
// every adjacent pair. Reordering or substituting a hue invalidates that, so
// re-validate before changing it. Two light-mode entries (orange, amber) sit
// just under 3:1 against white, which is why every chart using this palette
// carries visible labels rather than relying on colour alone.

export const CHART_SERIES_CLASSES = [
  "bg-blue-600 dark:bg-blue-600",
  "bg-orange-500 dark:bg-orange-600",
  "bg-teal-600 dark:bg-teal-600",
  "bg-amber-500 dark:bg-amber-600",
  "bg-pink-500 dark:bg-pink-500",
  "bg-green-600 dark:bg-green-600",
  "bg-violet-600 dark:bg-violet-500",
  "bg-red-500 dark:bg-red-500",
] as const;

// Anything past the last slot, and the uncategorized bucket, which is a real
// amount but not a category.
export const OTHER_SERIES_CLASS = "bg-stone-400 dark:bg-stone-500";

/** How many entities can carry their own colour before the rest fold together. */
export const MAX_SERIES = CHART_SERIES_CLASSES.length;

/**
 * The colour for a series at a stable position.
 *
 * The index must come from something that does not change with the selected
 * period — a group's own ordering, not its rank this month — so that changing
 * the range never repaints the groups that were already on screen.
 */
export function seriesClass(index: number): string {
  return CHART_SERIES_CLASSES[index] ?? OTHER_SERIES_CLASS;
}
