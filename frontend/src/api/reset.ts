import { api } from "./client";
import type { ResetOption } from "../components/ResetConfirmModal";

export type ResetResult = {
  deleted_transactions: number;
  deleted_assignments: number;
};

export const resetApi = {
  reset: (options: ResetOption[]) =>
    api<ResetResult>("/api/reset", { method: "POST", body: { options } }),
};
