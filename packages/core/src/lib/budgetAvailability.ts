export type AvailabilityState = "overspent" | "unassigned" | "funded" | "partial";

// Shared with anywhere that shows a category's remaining budget as a
// color-coded pill (the Budget page's Available column, the transaction
// modals' category picker) so the color rules can't drift between them.
export function availabilityState(assignedCents: number, balanceCents: number): AvailabilityState {
  if (balanceCents < 0) return "overspent";
  if (assignedCents === 0) return "unassigned";
  if (balanceCents >= assignedCents) return "funded";
  return "partial";
}
