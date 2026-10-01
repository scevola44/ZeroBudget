import { api } from "./client";
import type { Payee, PayeeCategoryRule } from "./types";

export const PAYEES_QUERY_KEY = ["payees"];
export const PAYEE_RULES_QUERY_KEY = ["payee-rules"];

export const payeesApi = {
  // Bounded high enough to show every payee on the Settings management list —
  // the same endpoint's default (20) is tuned for autocomplete-while-typing.
  list: () => api<Payee[]>("/api/payees?limit=200"),
  rename: (id: number, name: string) =>
    api<Payee>(`/api/payees/${id}`, { method: "PATCH", body: { name } }),
  merge: (targetId: number, sourceIds: number[]) =>
    api<{ reassigned: number }>(`/api/payees/${targetId}/merge`, {
      method: "POST",
      body: { source_ids: sourceIds },
    }),
};

export const payeeRulesApi = {
  list: () => api<PayeeCategoryRule[]>("/api/payee-rules"),
  create: (input: { category_id: number; contains_text: string; sort_order?: number }) =>
    api<PayeeCategoryRule>("/api/payee-rules", { method: "POST", body: input }),
  update: (
    id: number,
    input: Partial<{ category_id: number; contains_text: string; sort_order: number }>,
  ) => api<PayeeCategoryRule>(`/api/payee-rules/${id}`, { method: "PATCH", body: input }),
  remove: (id: number) => api<void>(`/api/payee-rules/${id}`, { method: "DELETE" }),
};
