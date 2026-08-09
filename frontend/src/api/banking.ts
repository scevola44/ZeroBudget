// Enable Banking HTTP helpers. Kept alongside the other ``api/`` modules so
// pages can import from one place.

import { api } from "./client";
import type { Scope } from "./types";

export type Aspsp = {
  name: string;
  country: string;
  logo: string | null;
};

export type BankConnection = {
  id: number;
  aspsp_name: string;
  aspsp_country: string;
  valid_until: string | null;
  last_synced_at: string | null;
  last_error_code: string | null;
};

export type ConnectResponse = {
  authorization_url: string;
  state: string;
};

export type SkippedAccount = {
  name: string;
  reason: string;
};

export type ConnectionSyncResult = {
  connection_id: number;
  aspsp_name: string;
  added: number;
  modified: number;
  skipped_pending: number;
  skipped_non_eur: number;
  skipped_unknown_account: number;
  skipped_unparseable_date: number;
  error_code: string | null;
  touched_account_ids: number[];
};

export type SyncStatus = {
  mode: "manual" | "auto";
  max_per_day: number;
  used_today: number;
  remaining_today: number;
  last_run_at: string | null;
  next_auto_sync_at: string | null;
};

export type GlobalSyncResponse = {
  status: "ok" | "partial" | "error";
  connections: ConnectionSyncResult[];
  quota: SyncStatus;
};

export type CallbackResponse = {
  connection: BankConnection;
  account_ids: number[];
  skipped_accounts: SkippedAccount[];
  sync: ConnectionSyncResult;
};

export const bankingApi = {
  listAspsps: () => api<Aspsp[]>("/api/banking/aspsps"),
  connect: (aspsp_name: string, aspsp_country: string, scope: Scope = "personal") =>
    api<ConnectResponse>("/api/banking/connections", {
      method: "POST",
      body: { aspsp_name, aspsp_country, scope },
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
