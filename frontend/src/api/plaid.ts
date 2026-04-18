// Plaid-linking HTTP helpers. Kept alongside the other ``api/`` modules so
// pages can import from one place.

import { api } from "./client";

export type LinkTokenResponse = { link_token: string };

export type PlaidItem = {
  id: number;
  institution_name: string | null;
  last_synced_at: string | null;
  last_error_code: string | null;
};

export type SkippedAccount = {
  plaid_account_id: string;
  name: string;
  reason: string;
};

export type SyncResponse = {
  added: number;
  modified: number;
  removed: number;
  skipped_pending: number;
  skipped_non_eur: number;
  skipped_unknown_account: number;
  last_synced_at: string | null;
  error_code: string | null;
  touched_account_ids: number[];
};

export type ExchangeResponse = {
  item: PlaidItem;
  account_ids: number[];
  skipped_accounts: SkippedAccount[];
  sync: SyncResponse;
};

export const plaidApi = {
  createLinkToken: () =>
    api<LinkTokenResponse>("/api/plaid/link-token", { method: "POST" }),
  exchangePublicToken: (public_token: string) =>
    api<ExchangeResponse>("/api/plaid/exchange", {
      method: "POST",
      body: { public_token },
    }),
  syncItem: (itemId: number) =>
    api<SyncResponse>(`/api/plaid/items/${itemId}/sync`, { method: "POST" }),
  unlinkItem: (itemId: number) =>
    api<void>(`/api/plaid/items/${itemId}`, { method: "DELETE" }),
  listItems: () => api<PlaidItem[]>("/api/plaid/items"),
};
