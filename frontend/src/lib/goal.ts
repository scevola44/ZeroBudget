import type { BudgetCategoryRow, GoalKind } from "../api/types";
import { monthLabel } from "./dates";
import { formatCents } from "./money";

type GoalShape = {
  goal_kind: GoalKind;
  goal_amount_cents: number;
  goal_target_month: string | null;
};

export function monthlyGoalCents(cat: BudgetCategoryRow): number {
  switch (cat.goal_kind) {
    case "monthly": return cat.goal_amount_cents;
    case "yearly":  return Math.round(cat.goal_amount_cents / 12);
    case "target_date": return cat.needed_this_month_cents ?? 0;
  }
}

export function formatGoal(goal: GoalShape): string {
  const amount = formatCents(goal.goal_amount_cents);
  switch (goal.goal_kind) {
    case "monthly":
      return `${amount} / month`;
    case "yearly":
      return `${amount} / year`;
    case "target_date":
      if (!goal.goal_target_month) return amount;
      // API returns "YYYY-MM-DD"; monthLabel wants "YYYY-MM".
      return `${amount} by ${monthLabel(goal.goal_target_month.slice(0, 7))}`;
  }
}
