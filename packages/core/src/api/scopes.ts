import { api } from "./client";
import type { Scope } from "./types";

export const SCOPES_QUERY_KEY = ["scopes"];

export const scopesApi = {
  list: () => api<Scope[]>("/api/scopes"),
  create: (name: string) =>
    api<Scope>("/api/scopes", { method: "POST", body: { name } }),
  rename: (id: number, name: string) =>
    api<Scope>(`/api/scopes/${id}`, { method: "PATCH", body: { name } }),
  remove: (id: number) => api<void>(`/api/scopes/${id}`, { method: "DELETE" }),
};
