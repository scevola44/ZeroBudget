import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { usePlaidLink } from "react-plaid-link";

import { api, ApiError } from "../api/client";
import { plaidApi } from "../api/plaid";
import type { ExchangeResponse, SyncResponse } from "../api/plaid";
import type { Account, Scope } from "../api/types";
import { scopeLabel } from "../api/types";
import { formatCents } from "../lib/money";

function ScopeChip({ scope }: { scope: Scope }) {
  const cls =
    scope === "shared"
      ? "bg-violet-100 text-violet-800 dark:bg-violet-900/50 dark:text-violet-200"
      : "bg-sky-100 text-sky-800 dark:bg-sky-900/50 dark:text-sky-200";
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}>
      {scopeLabel(scope)}
    </span>
  );
}

export function AccountsPage() {
  const qc = useQueryClient();
  const accountsQuery = useQuery<Account[]>({
    queryKey: ["accounts"],
    queryFn: () => api<Account[]>("/api/accounts"),
  });

  const [name, setName] = useState("");
  const [type, setType] = useState("checking");
  const [scope, setScope] = useState<Scope>("personal");
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: (body: { name: string; type: string; scope: Scope }) =>
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
        className="bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 rounded-2xl p-5 flex flex-col sm:flex-row gap-3 sm:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim()) createMutation.mutate({ name: name.trim(), type, scope });
        }}
      >
        <div className="flex-1 space-y-1">
          <label className="text-sm font-medium text-stone-700 dark:text-stone-300">Name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            placeholder="e.g. Checking"
            className="w-full border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium text-stone-700 dark:text-stone-300">Type</label>
          <select
            value={type}
            onChange={(e) => setType(e.target.value)}
            className="border border-stone-300 dark:border-stone-600 rounded-lg px-3 py-2 bg-white dark:bg-stone-900"
          >
            <option value="checking">Checking</option>
            <option value="savings">Savings</option>
            <option value="cash">Cash</option>
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium text-stone-700 dark:text-stone-300">Scope</label>
          <select
            value={scope}
            onChange={(e) => setScope(e.target.value as Scope)}
            className="border border-stone-300 dark:border-stone-600 rounded-lg px-3 py-2 bg-white dark:bg-stone-900"
          >
            <option value="personal">Personal</option>
            <option value="shared">Family</option>
          </select>
        </div>
        <button
          type="submit"
          disabled={createMutation.isPending}
          className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 dark:bg-indigo-500 dark:hover:bg-indigo-600 text-white font-medium rounded-lg px-4 py-2"
        >
          Add account
        </button>
      </form>

      {feedback && (
        <div className="bg-emerald-50 dark:bg-emerald-900/30 border border-emerald-200 dark:border-emerald-800 text-emerald-800 dark:text-emerald-200 rounded-xl px-4 py-3 text-sm">
          {feedback}
        </div>
      )}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-800 dark:text-red-200 rounded-xl px-4 py-3 text-sm">
          {error}
        </div>
      )}

      <div className="bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 rounded-2xl overflow-hidden">
        {accountsQuery.isLoading && <div className="p-5 text-stone-500 dark:text-stone-400">Loading…</div>}
        {accountsQuery.data && accountsQuery.data.length === 0 && (
          <div className="p-5 text-stone-500 dark:text-stone-400">No accounts yet. Add one above or link a bank.</div>
        )}
        {accountsQuery.data && accountsQuery.data.length > 0 && (
          <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase text-stone-500 dark:text-stone-400">
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
    <tr className="border-t border-stone-100 dark:border-stone-800">
      <td className="px-5 py-3">
        <div className="flex items-center gap-2">
          <Link to={`/accounts/${account.id}`} className="text-indigo-600 dark:text-indigo-400 hover:underline">
            {account.name}
          </Link>
          <ScopeChip scope={account.scope} />
        </div>
        {account.plaid_mask && (
          <span className="text-xs text-stone-400 dark:text-stone-500">••{account.plaid_mask}</span>
        )}
      </td>
      <td className="hidden sm:table-cell px-5 py-3 capitalize text-stone-600 dark:text-stone-400">{account.type}</td>
      <td className="hidden sm:table-cell px-5 py-3 text-stone-600 dark:text-stone-400">
        {account.institution_name ?? <span className="text-stone-400 dark:text-stone-500">Manual</span>}
      </td>
      <td className="px-5 py-3 text-right tabular-nums">{formatCents(account.balance_cents)}</td>
      <td className="px-5 py-3 text-right space-x-2">
        {isLinked && account.plaid_item_id !== null && (
          <>
            <button
              onClick={() => syncMutation.mutate(account.plaid_item_id!)}
              disabled={syncMutation.isPending}
              className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline disabled:text-stone-400 dark:disabled:text-stone-500 px-2 py-1"
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
              className="text-xs text-red-600 dark:text-red-400 hover:underline disabled:text-stone-400 dark:disabled:text-stone-500 px-2 py-1"
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
    <div className="bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 rounded-2xl p-5 flex items-center justify-between gap-4">
      <div>
        <div className="font-medium">Link a bank account</div>
        <div className="text-sm text-stone-500 dark:text-stone-400">
          Import transactions automatically via Plaid. EUR accounts only.
        </div>
      </div>
      <button
        onClick={handleClick}
        disabled={isRequesting || Boolean(linkToken)}
        className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 dark:bg-indigo-500 dark:hover:bg-indigo-600 text-white font-medium rounded-lg px-4 py-2"
      >
        {isRequesting ? "Loading…" : linkToken ? "Opening…" : "Link bank account"}
      </button>
    </div>
  );
}
