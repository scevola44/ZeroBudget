import { api } from "./client";

export type ResetOption = "transactions" | "assignments";

export type ResetResult = {
  deleted_transactions: number;
  deleted_assignments: number;
};

export const resetApi = {
  reset: (options: ResetOption[]) =>
    api<ResetResult>("/api/reset", { method: "POST", body: { options } }),
};
