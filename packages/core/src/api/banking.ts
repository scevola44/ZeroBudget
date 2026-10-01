// Enable Banking HTTP helpers. Kept alongside the other ``api/`` modules so
// pages can import from one place.

import { api } from "./client";
import type { components } from "../generated/schema";

type Schemas = components["schemas"];

export type Aspsp = Schemas["AspspResponse"];
export type BankConnection = Schemas["BankConnectionResponse"];
export type ConnectResponse = Schemas["ConnectResponse"];
export type SkippedAccount = Schemas["SkippedAccount"];
export type ConnectionSyncResult = Schemas["ConnectionSyncResult"];
export type SyncStatus = Schemas["SyncStatusResponse"];
export type GlobalSyncResponse = Schemas["GlobalSyncResponse"];
export type CallbackResponse = Schemas["CallbackResponse"];

export const bankingApi = {
  listAspsps: () => api<Aspsp[]>("/api/banking/aspsps"),
  connect: (aspsp_name: string, aspsp_country: string, scope_id: number) =>
    api<ConnectResponse>("/api/banking/connections", {
      method: "POST",
      body: { aspsp_name, aspsp_country, scope_id },
    }),
  completeCallback: (code: string, state: string) =>
    api<CallbackResponse>("/api/banking/connections/callback", {
      method: "POST",
      body: { code, state },
    }),
  syncNow: () => api<GlobalSyncResponse>("/api/banking/sync", { method: "POST" }),
  syncStatus: () => api<SyncStatus>("/api/banking/sync/status"),
  listConnections: () => api<BankConnection[]>("/api/banking/connections"),
  unlinkConnection: (connectionId: number) =>
    api<void>(`/api/banking/connections/${connectionId}`, { method: "DELETE" }),
};
