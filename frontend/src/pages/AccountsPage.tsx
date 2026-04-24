import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { usePlaidLink } from "react-plaid-link";

import { api, ApiError } from "../api/client";
import { plaidApi } from "../api/plaid";
import type { ExchangeResponse, SyncResponse } from "../api/plaid";
import type { Account } from "../api/types";
import { formatCents } from "../lib/money";

export function AccountsPage() {
  const qc = useQueryClient();
  const accountsQuery = useQuery<Account[]>({
    queryKey: ["accounts"],
    queryFn: () => api<Account[]>("/api/accounts"),
  });

  const [name, setName] = useState("");
  const [type, setType] = useState("checking");
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: (body: { name: string; type: string }) =>
      api<Account>("/api/accounts", { method: "POST", body }),
    onSuccess: () => {
      setName("");
      void qc.invalidateQueries({ queryKey: ["accounts"] });
    },
  });

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold">Accounts</h1>

      <PlaidLinkCard
        onLinked={(summary) => {
          const skipped = summary.skipped_accounts.length;
          setFeedback(
            `Linked ${summary.account_ids.length} account(s) · imported ${summary.sync.added} transaction(s)` +
              (skipped ? ` · skipped ${skipped} non-EUR account(s)` : "")
          );
          setError(null);
          void qc.invalidateQueries({ queryKey: ["accounts"] });
          void qc.invalidateQueries({ queryKey: ["transactions"] });
          void qc.invalidateQueries({ queryKey: ["budget"] });
        }}
        onError={(message) => {
          setError(message);
          setFeedback(null);
        }}
      />

      <form
        className="bg-white border border-slate-200 rounded-2xl p-5 flex flex-col sm:flex-row gap-3 sm:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim()) createMutation.mutate({ name: name.trim(), type });
        }}
      >
        <div className="flex-1 space-y-1">
          <label className="text-sm font-medium text-slate-700">Name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            placeholder="e.g. Checking"
            className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium text-slate-700">Type</label>
          <select
            value={type}
            onChange={(e) => setType(e.target.value)}
            className="border border-slate-300 rounded-lg px-3 py-2 bg-white"
          >
            <option value="checking">Checking</option>
            <option value="savings">Savings</option>
            <option value="cash">Cash</option>
          </select>
        </div>
        <button
          type="submit"
          disabled={createMutation.isPending}
          className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white font-medium rounded-lg px-4 py-2"
        >
          Add account
        </button>
      </form>

      {feedback && (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-xl px-4 py-3 text-sm">
          {feedback}
        </div>
      )}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-800 rounded-xl px-4 py-3 text-sm">
          {error}
        </div>
      )}

      <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
        {accountsQuery.isLoading && <div className="p-5 text-slate-500">Loading…</div>}
        {accountsQuery.data && accountsQuery.data.length === 0 && (
          <div className="p-5 text-slate-500">No accounts yet. Add one above or link a bank.</div>
        )}
        {accountsQuery.data && accountsQuery.data.length > 0 && (
          <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr>
                <th className="text-left px-5 py-2">Name</th>
                <th className="hidden sm:table-cell text-left px-5 py-2">Type</th>
                <th className="hidden sm:table-cell text-left px-5 py-2">Bank</th>
                <th className="text-right px-5 py-2">Balance</th>
                <th className="px-5 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {accountsQuery.data.map((a) => (
                <AccountRow
                  key={a.id}
                  account={a}
                  onSynced={(summary) => {
                    setFeedback(
                      `Synced · +${summary.added} added, ${summary.modified} updated, ${summary.removed} removed`
                    );
                    setError(null);
                  }}
                  onUnlinked={() => {
                    setFeedback("Bank unlinked.");
                    setError(null);
                  }}
                  onError={(message) => {
                    setError(message);
                    setFeedback(null);
                  }}
                />
              ))}
            </tbody>
          </table>
          </div>
        )}
      </div>
    </div>
  );
}

function AccountRow({
  account,
  onSynced,
  onUnlinked,
  onError,
}: {
  account: Account;
  onSynced: (summary: SyncResponse) => void;
  onUnlinked: () => void;
  onError: (message: string) => void;
}) {
  const qc = useQueryClient();

  const syncMutation = useMutation({
    mutationFn: (itemId: number) => plaidApi.syncItem(itemId),
    onSuccess: (summary) => {
      onSynced(summary);
      void qc.invalidateQueries({ queryKey: ["accounts"] });
      void qc.invalidateQueries({ queryKey: ["transactions"] });
      void qc.invalidateQueries({ queryKey: ["budget"] });
    },
    onError: (err) => onError(err instanceof Error ? err.message : "Sync failed"),
  });

  const unlinkMutation = useMutation({
    mutationFn: (itemId: number) => plaidApi.unlinkItem(itemId),
    onSuccess: () => {
      onUnlinked();
      void qc.invalidateQueries({ queryKey: ["accounts"] });
      void qc.invalidateQueries({ queryKey: ["transactions"] });
      void qc.invalidateQueries({ queryKey: ["budget"] });
    },
    onError: (err) => onError(err instanceof Error ? err.message : "Unlink failed"),
  });

  const isLinked = account.plaid_item_id !== null;

  return (
    <tr className="border-t border-slate-100">
      <td className="px-5 py-3">
        <Link to={`/accounts/${account.id}`} className="text-indigo-600 hover:underline">
          {account.name}
        </Link>
        {account.plaid_mask && (
          <span className="ml-2 text-xs text-slate-400">••{account.plaid_mask}</span>
        )}
      </td>
      <td className="hidden sm:table-cell px-5 py-3 capitalize text-slate-600">{account.type}</td>
      <td className="hidden sm:table-cell px-5 py-3 text-slate-600">
        {account.institution_name ?? <span className="text-slate-400">Manual</span>}
      </td>
      <td className="px-5 py-3 text-right tabular-nums">{formatCents(account.balance_cents)}</td>
      <td className="px-5 py-3 text-right space-x-2">
        {isLinked && account.plaid_item_id !== null && (
          <>
            <button
              onClick={() => syncMutation.mutate(account.plaid_item_id!)}
              disabled={syncMutation.isPending}
              className="text-xs text-indigo-600 hover:underline disabled:text-slate-400 px-2 py-1"
            >
              {syncMutation.isPending ? "Syncing…" : "Sync"}
            </button>
            <button
              onClick={() => {
                if (confirm("Unlink this bank? Its accounts and imported transactions will be deleted.")) {
                  unlinkMutation.mutate(account.plaid_item_id!);
                }
              }}
              disabled={unlinkMutation.isPending}
              className="text-xs text-red-600 hover:underline disabled:text-slate-400 px-2 py-1"
            >
              Unlink
            </button>
          </>
        )}
      </td>
    </tr>
  );
}

function PlaidLinkCard({
  onLinked,
  onError,
}: {
  onLinked: (summary: ExchangeResponse) => void;
  onError: (message: string) => void;
}) {
  const [linkToken, setLinkToken] = useState<string | null>(null);
  const [isRequesting, setIsRequesting] = useState(false);

  const onSuccess = useCallback(
    async (public_token: string) => {
      try {
        const resp = await plaidApi.exchangePublicToken(public_token);
        onLinked(resp);
      } catch (err) {
        onError(err instanceof Error ? err.message : "Failed to link bank");
      } finally {
        setLinkToken(null);
      }
    },
    [onLinked, onError]
  );

  const { open, ready } = usePlaidLink({
    token: linkToken,
    onSuccess,
    onExit: () => setLinkToken(null),
  });

  const handleClick = async () => {
    setIsRequesting(true);
    try {
      const { link_token } = await plaidApi.createLinkToken();
      setLinkToken(link_token);
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        onError("Plaid is not configured on the server. Set PLAID_CLIENT_ID / PLAID_SECRET to enable bank linking.");
      } else {
        onError(err instanceof Error ? err.message : "Could not start bank link");
      }
    } finally {
      setIsRequesting(false);
    }
  };

  // Auto-open Plaid Link once the token is set and the SDK is ready.
  useEffect(() => {
    if (linkToken && ready) {
      open();
    }
  }, [linkToken, ready, open]);

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5 flex items-center justify-between gap-4">
      <div>
        <div className="font-medium">Link a bank account</div>
        <div className="text-sm text-slate-500">
          Import transactions automatically via Plaid. EUR accounts only.
        </div>
      </div>
      <button
        onClick={handleClick}
        disabled={isRequesting || Boolean(linkToken)}
        className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white font-medium rounded-lg px-4 py-2"
      >
        {isRequesting ? "Loading…" : linkToken ? "Opening…" : "Link bank account"}
      </button>
    </div>
  );
}
