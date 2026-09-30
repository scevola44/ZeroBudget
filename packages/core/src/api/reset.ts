import type { components } from "../generated/schema";
import { api } from "./client";

type Schemas = components["schemas"];

export type ResetOption = Schemas["ResetOption"];
export type ResetResult = Schemas["ResetResponse"];

export const resetApi = {
  reset: (options: ResetOption[]) =>
    api<ResetResult>("/api/reset", { method: "POST", body: { options } }),
};
