import { api } from "./client";
import type { BudgetMonth, FundGoalsPreview } from "./types";

export const budgetApi = {
  get: (month: string) => api<BudgetMonth>(`/api/budget/${month}`),
  assign: (month: string, categoryId: number, amountCents: number) =>
    api(`/api/budget/${month}/assign`, {
      method: "POST",
      body: { category_id: categoryId, amount_cents: amountCents },
    }),
  previewFundGoals: (month: string, scopeId: number) =>
    api<FundGoalsPreview>(`/api/budget/${month}/fund-goals/preview`, {
      method: "POST",
      body: { scope_id: scopeId },
    }),
  commitFundGoals: (month: string, scopeId: number) =>
    api<void>(`/api/budget/${month}/fund-goals`, {
      method: "POST",
      body: { scope_id: scopeId },
    }),
  moveMoney: (month: string, fromCategoryId: number, toCategoryId: number, amountCents: number) =>
    api<void>(`/api/budget/${month}/move`, {
      method: "POST",
      body: {
        from_category_id: fromCategoryId,
        to_category_id: toCategoryId,
        amount_cents: amountCents,
      },
    }),
};
