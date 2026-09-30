import { availabilityState, type AvailabilityState } from "@zerobudget/core";

const PILL_CLASS_BY_STATE: Record<AvailabilityState, string> = {
  overspent: "bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-200",
  unassigned: "bg-stone-200 text-stone-600 dark:bg-stone-800 dark:text-stone-300",
  funded: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-200",
  partial: "bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200",
};

export function availablePillClass(assignedCents: number, balanceCents: number): string {
  return PILL_CLASS_BY_STATE[availabilityState(assignedCents, balanceCents)];
}
