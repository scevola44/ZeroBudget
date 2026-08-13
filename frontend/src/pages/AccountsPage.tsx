import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../api/client";
import { bankingApi } from "../api/banking";
import type { Aspsp, BankConnection, SyncStatus } from "../api/banking";
import { MANUAL_ACCOUNT_TYPES, type Account } from "../api/types";
import { EditAccountModal, type AccountEdit } from "../components/EditAccountModal";
import { ScopeChip } from "../components/ScopeChip";
import { ScopeSelect } from "../components/ScopeSelect";
import { useScopes } from "../lib/useScopes";
import { formatCents } from "../lib/money";

const CONSENT_EXPIRY_WARNING_DAYS = 7;

function connectionNeedsReauth(connection: BankConnection): boolean {
  if (connection.last_error_code === "SESSION_EXPIRED") return true;
  if (!connection.valid_until) return false;
  const expiresInMs = new Date(connection.valid_until).getTime() - Date.now();
  return expiresInMs < CONSENT_EXPIRY_WARNING_DAYS * 24 * 60 * 60 * 1000;
}

export function AccountsPage() {
  const qc = useQueryClient();
  const accountsQuery = useQuery<Account[]>({
    queryKey: ["accounts"],
    queryFn: () => api<Account[]>("/api/accounts"),
  });
  const connectionsQuery = useQuery<BankConnection[]>({
    queryKey: ["bank-connections"],
    queryFn: bankingApi.listConnections,
  });

  const [name, setName] = useState("");
  const [type, setType] = useState("checking");
  // Null until the scopes query lands; `scopeId` below falls back to the
  // user's first scope so the form is usable the moment it renders.
  const [pickedScopeId, setPickedScopeId] = useState<number | null>(null);
  const { defaultScopeId } = useScopes();
  const scopeId = pickedScopeId ?? defaultScopeId;
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editingAccountId, setEditingAccountId] = useState<number | null>(null);
  const [editError, setEditError] = useState<string | null>(null);
  const [showClosed, setShowClosed] = useState(false);

  const createMutation = useMutation({
    mutationFn: (body: { name: string; type: string; scope_id: number }) =>
      api<Account>("/api/accounts", { method: "POST", body }),
    onSuccess: () => {
      setName("");
      void qc.invalidateQueries({ queryKey: ["accounts"] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: (vars: { accountId: number; edit: AccountEdit }) =>
      api<Account>(`/api/accounts/${vars.accountId}`, {
        method: "PATCH",
        body: vars.edit,
      }),
    onSuccess: () => {
      setEditingAccountId(null);
      setEditError(null);
      void qc.invalidateQueries({ queryKey: ["accounts"] });
      void qc.invalidateQueries({ queryKey: ["budget"] });
    },
    onError: (err) => setEditError(err instanceof Error ? err.message : "Update failed"),
  });

  const openAccounts = (accountsQuery.data ?? []).filter((a) => !a.closed);
  const closedAccounts = (accountsQuery.data ?? []).filter((a) => a.closed);
  const visibleAccounts = showClosed
    ? [...openAccounts, ...closedAccounts]
    : openAccounts;

  const connectionsNeedingReauth = (connectionsQuery.data ?? []).filter(connectionNeedsReauth);

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold">Accounts</h1>

      <BankLinkCard
        onFeedback={(message) => {
          setFeedback(message);
          setError(null);
        }}
        onError={(message) => {
          setError(message);
          setFeedback(null);
        }}
      />

      {connectionsNeedingReauth.map((connection) => (
        <ReauthBanner
          key={connection.id}
          connection={connection}
          scopeId={
            (accountsQuery.data ?? []).find((a) => a.bank_connection_id === connection.id)
              ?.scope_id ?? null
          }
          onError={setError}
        />
      ))}

      <form
        className="bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 rounded-2xl p-5 flex flex-col sm:flex-row gap-3 sm:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim() && scopeId !== null)
            createMutation.mutate({ name: name.trim(), type, scope_id: scopeId });
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
          <div className="relative">
            <select
              value={type}
              onChange={(e) => setType(e.target.value)}
              className="h-9 w-full appearance-none border border-stone-300 dark:border-stone-600 rounded-lg pl-3 pr-8 bg-white dark:bg-stone-900"
            >
              {MANUAL_ACCOUNT_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
            <div className="pointer-events-none absolute inset-y-0 right-2 flex items-center text-stone-400 dark:text-stone-500">
              <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 6l4 4 4-4" />
              </svg>
            </div>
          </div>
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium text-stone-700 dark:text-stone-300">Scope</label>
          <ScopeSelect value={scopeId} onChange={setPickedScopeId} />
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
          <div className="p-5 text-stone-500 dark:text-stone-400">No accounts yet. Add one above or connect a bank.</div>
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
              {visibleAccounts.map((a) => (
                <AccountRow
                  key={a.id}
                  account={a}
                  onEdit={() => {
                    setEditError(null);
                    setEditingAccountId(a.id);
                  }}
                  onUnlinked={() => {
                    setFeedback("Bank disconnected.");
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
        {closedAccounts.length > 0 && (
          <div className="border-t border-stone-100 dark:border-stone-800 px-5 py-3">
            <button
              onClick={() => setShowClosed((v) => !v)}
              className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline"
            >
              {showClosed
                ? "Hide closed accounts"
                : `Show closed accounts (${closedAccounts.length})`}
            </button>
          </div>
        )}
      </div>

      {editingAccountId !== null && accountsQuery.data && (
        <EditAccountModal
          account={accountsQuery.data.find((a) => a.id === editingAccountId)!}
          isOpen={true}
          onClose={() => {
            setEditingAccountId(null);
            setEditError(null);
          }}
          onSave={(edit) => {
            updateMutation.mutate({ accountId: editingAccountId, edit });
          }}
          isPending={updateMutation.isPending}
          error={editError}
        />
      )}
    </div>
  );
}

function AccountRow({
  account,
  onEdit,
  onUnlinked,
  onError,
}: {
  account: Account;
  onEdit: () => void;
  onUnlinked: () => void;
  onError: (message: string) => void;
}) {
  const qc = useQueryClient();

  const unlinkMutation = useMutation({
    mutationFn: (connectionId: number) => bankingApi.unlinkConnection(connectionId),
    onSuccess: () => {
      onUnlinked();
      void qc.invalidateQueries({ queryKey: ["accounts"] });
      void qc.invalidateQueries({ queryKey: ["transactions"] });
      void qc.invalidateQueries({ queryKey: ["budget"] });
      void qc.invalidateQueries({ queryKey: ["bank-connections"] });
    },
    onError: (err) => onError(err instanceof Error ? err.message : "Disconnect failed"),
  });

  // The server refuses to delete an account that has transactions — closing is
  // the way to retire those. Its message is what the user sees.
  const deleteMutation = useMutation({
    mutationFn: () => api(`/api/accounts/${account.id}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["accounts"] });
      void qc.invalidateQueries({ queryKey: ["budget"] });
    },
    onError: (err) => onError(err instanceof Error ? err.message : "Delete failed"),
  });

  return (
    <tr
      className={`border-t border-stone-100 dark:border-stone-800 ${
        account.closed ? "opacity-60" : ""
      }`}
    >
      <td className="px-5 py-3">
        <div className="flex items-center gap-2">
          <Link to={`/accounts/${account.id}`} className="text-indigo-600 dark:text-indigo-400 hover:underline">
            {account.name}
          </Link>
          <ScopeChip scopeId={account.scope_id} />
          {account.closed && (
            <span className="text-xs rounded-full px-2 py-0.5 bg-stone-100 dark:bg-stone-800 text-stone-500 dark:text-stone-400">
              Closed
            </span>
          )}
        </div>
        {account.bank_account_mask && (
          <span className="text-xs text-stone-400 dark:text-stone-500">••{account.bank_account_mask}</span>
        )}
      </td>
      <td className="hidden sm:table-cell px-5 py-3 capitalize text-stone-600 dark:text-stone-400">{account.type}</td>
      <td className="hidden sm:table-cell px-5 py-3 text-stone-600 dark:text-stone-400">
        {account.institution_name ?? <span className="text-stone-400 dark:text-stone-500">Manual</span>}
      </td>
      <td className="px-5 py-3 text-right tabular-nums">{formatCents(account.balance_cents)}</td>
      <td className="px-5 py-3 text-right space-x-2">
        <button
          onClick={onEdit}
          className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline px-2 py-1"
        >
          Edit
        </button>
        {account.bank_connection_id !== null ? (
          <button
            onClick={() => {
              if (confirm("Disconnect this bank? Its accounts and imported transactions will be deleted.")) {
                unlinkMutation.mutate(account.bank_connection_id!);
              }
            }}
            disabled={unlinkMutation.isPending}
            className="text-xs text-red-600 dark:text-red-400 hover:underline disabled:text-stone-400 dark:disabled:text-stone-500 px-2 py-1"
          >
            Disconnect
          </button>
        ) : (
          <button
            onClick={() => deleteMutation.mutate()}
            disabled={deleteMutation.isPending}
            className="text-xs text-red-600 dark:text-red-400 hover:underline disabled:text-stone-400 dark:disabled:text-stone-500 px-2 py-1"
          >
            Delete
          </button>
        )}
      </td>
    </tr>
  );
}

function ReauthBanner({
  connection,
  scopeId,
  onError,
}: {
  connection: BankConnection;
  scopeId: number | null;
  onError: (message: string) => void;
}) {
  const [isRedirecting, setIsRedirecting] = useState(false);

  const reconnect = async () => {
    // The banner only renders for a connection that already has an account, so
    // the scope is known; the guard is for the moment before the query lands.
    if (scopeId === null) return;
    setIsRedirecting(true);
    try {
      const { authorization_url } = await bankingApi.connect(
        connection.aspsp_name,
        connection.aspsp_country,
        scopeId,
      );
      window.location.href = authorization_url;
    } catch (err) {
      setIsRedirecting(false);
      onError(err instanceof Error ? err.message : "Could not start bank re-authorization");
    }
  };

  const expired = connection.last_error_code === "SESSION_EXPIRED";
  return (
    <div className="bg-amber-50 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-200 rounded-xl px-4 py-3 text-sm flex items-center justify-between gap-4">
      <span>
        {expired
          ? `Access to ${connection.aspsp_name} has expired.`
          : `Access to ${connection.aspsp_name} expires soon.`}{" "}
        Re-authorize at your bank to keep syncing.
      </span>
      <button
        onClick={() => void reconnect()}
        disabled={isRedirecting}
        className="shrink-0 bg-amber-600 hover:bg-amber-700 disabled:bg-amber-400 text-white font-medium rounded-lg px-3 py-1.5 text-xs"
      >
        {isRedirecting ? "Redirecting…" : "Reconnect"}
      </button>
    </div>
  );
}

function BankLinkCard({
  onFeedback,
  onError,
}: {
  onFeedback: (message: string) => void;
  onError: (message: string) => void;
}) {
  const qc = useQueryClient();
  const [isPicking, setIsPicking] = useState(false);
  const [country, setCountry] = useState("");
  const [aspspName, setAspspName] = useState("");
  const [pickedLinkScopeId, setPickedLinkScopeId] = useState<number | null>(null);
  const { defaultScopeId } = useScopes();
  const linkScopeId = pickedLinkScopeId ?? defaultScopeId;
  const [isRedirecting, setIsRedirecting] = useState(false);

  const statusQuery = useQuery<SyncStatus>({
    queryKey: ["sync-status"],
    queryFn: bankingApi.syncStatus,
  });
  const aspspsQuery = useQuery<Aspsp[]>({
    queryKey: ["aspsps"],
    queryFn: bankingApi.listAspsps,
    enabled: isPicking,
    staleTime: 24 * 60 * 60 * 1000,
    retry: false,
  });

  const countries = useMemo(
    () => [...new Set((aspspsQuery.data ?? []).map((a) => a.country))].sort(),
    [aspspsQuery.data]
  );
  const banks = useMemo(
    () => (aspspsQuery.data ?? []).filter((a) => a.country === country),
    [aspspsQuery.data, country]
  );

  const syncMutation = useMutation({
    mutationFn: bankingApi.syncNow,
    onSuccess: (result) => {
      const added = result.connections.reduce((sum, c) => sum + c.added, 0);
      const modified = result.connections.reduce((sum, c) => sum + c.modified, 0);
      const failed = result.connections.filter((c) => c.error_code !== null);
      let message = `Synced · +${added} added, ${modified} updated · ${result.quota.remaining_today} sync(s) left today`;
      if (failed.length > 0) {
        message += ` · failed: ${failed.map((c) => c.aspsp_name).join(", ")}`;
      }
      onFeedback(message);
      void qc.invalidateQueries({ queryKey: ["accounts"] });
      void qc.invalidateQueries({ queryKey: ["transactions"] });
      void qc.invalidateQueries({ queryKey: ["budget"] });
      void qc.invalidateQueries({ queryKey: ["bank-connections"] });
      void qc.invalidateQueries({ queryKey: ["sync-status"] });
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 429) {
        onError(err.message);
      } else {
        onError(err instanceof Error ? err.message : "Sync failed");
      }
      void qc.invalidateQueries({ queryKey: ["sync-status"] });
    },
  });

  const startConnect = async () => {
    if (!aspspName || !country || linkScopeId === null) return;
    setIsRedirecting(true);
    try {
      const { authorization_url } = await bankingApi.connect(
        aspspName,
        country,
        linkScopeId,
      );
      window.location.href = authorization_url;
    } catch (err) {
      setIsRedirecting(false);
      if (err instanceof ApiError && err.status === 503) {
        onError(
          "Enable Banking is not configured on the server. Set ENABLE_BANKING_APP_ID / ENABLE_BANKING_PRIVATE_KEY to enable bank connections."
        );
      } else {
        onError(err instanceof Error ? err.message : "Could not start bank connection");
      }
    }
  };

  const status = statusQuery.data;
  const quotaExhausted = status !== undefined && status.remaining_today <= 0;

  return (
    <div className="bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 rounded-2xl p-5 space-y-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <div className="font-medium">Connect a bank</div>
          <div className="text-sm text-stone-500 dark:text-stone-400">
            Import transactions via Enable Banking (PSD2). EUR accounts only.
          </div>
        </div>
        <div className="flex items-center gap-2">
          {status && (
            <button
              onClick={() => syncMutation.mutate()}
              disabled={syncMutation.isPending || quotaExhausted}
              title={
                status.mode === "auto"
                  ? "Automatic sync is on; manual runs share the same daily limit."
                  : undefined
              }
              className="border border-indigo-600 dark:border-indigo-400 text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 disabled:border-stone-300 disabled:text-stone-400 dark:disabled:border-stone-600 dark:disabled:text-stone-500 font-medium rounded-lg px-4 py-2"
            >
              {syncMutation.isPending
                ? "Syncing…"
                : quotaExhausted
                  ? "Daily limit reached"
                  : `Sync now (${status.remaining_today} left today)`}
            </button>
          )}
          <button
            onClick={() => setIsPicking((v) => !v)}
            className="bg-indigo-600 hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600 text-white font-medium rounded-lg px-4 py-2"
          >
            {isPicking ? "Cancel" : "Connect bank"}
          </button>
        </div>
      </div>

      {status?.mode === "auto" && (
        <div className="text-xs text-stone-500 dark:text-stone-400">
          Automatic sync: up to {status.max_per_day}×/day
          {status.next_auto_sync_at &&
            ` · next around ${new Date(status.next_auto_sync_at).toLocaleTimeString()}`}
        </div>
      )}

      {isPicking && (
        <div className="flex flex-col sm:flex-row gap-3 sm:items-end border-t border-stone-100 dark:border-stone-800 pt-4">
          {aspspsQuery.isLoading && (
            <div className="text-sm text-stone-500 dark:text-stone-400">Loading banks…</div>
          )}
          {aspspsQuery.isError && (
            <div className="text-sm text-red-600 dark:text-red-400">
              {aspspsQuery.error instanceof ApiError && aspspsQuery.error.status === 503
                ? "Enable Banking is not configured on the server."
                : "Could not load the bank list."}
            </div>
          )}
          {aspspsQuery.data && (
            <>
              <div className="space-y-1">
                <label className="text-sm font-medium text-stone-700 dark:text-stone-300">Country</label>
                <div className="relative">
                  <select
                    value={country}
                    onChange={(e) => {
                      setCountry(e.target.value);
                      setAspspName("");
                    }}
                    className="h-9 w-full appearance-none border border-stone-300 dark:border-stone-600 rounded-lg pl-3 pr-8 bg-white dark:bg-stone-900"
                  >
                    <option value="">Select…</option>
                    {countries.map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                  <div className="pointer-events-none absolute inset-y-0 right-2 flex items-center text-stone-400 dark:text-stone-500">
                    <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M4 6l4 4 4-4" />
                    </svg>
                  </div>
                </div>
              </div>
              <div className="flex-1 space-y-1">
                <label className="text-sm font-medium text-stone-700 dark:text-stone-300">Bank</label>
                <div className="relative">
                  <select
                    value={aspspName}
                    onChange={(e) => setAspspName(e.target.value)}
                    disabled={!country}
                    className="h-9 w-full appearance-none border border-stone-300 dark:border-stone-600 rounded-lg pl-3 pr-8 bg-white dark:bg-stone-900 disabled:text-stone-400 dark:disabled:text-stone-500"
                  >
                    <option value="">{country ? "Select…" : "Pick a country first"}</option>
                    {banks.map((b) => (
                      <option key={b.name} value={b.name}>{b.name}</option>
                    ))}
                  </select>
                  <div className="pointer-events-none absolute inset-y-0 right-2 flex items-center text-stone-400 dark:text-stone-500">
                    <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M4 6l4 4 4-4" />
                    </svg>
                  </div>
                </div>
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium text-stone-700 dark:text-stone-300">Scope</label>
                <ScopeSelect value={linkScopeId} onChange={setPickedLinkScopeId} />
              </div>
              <button
                onClick={() => void startConnect()}
                disabled={!aspspName || isRedirecting}
                className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 dark:bg-indigo-500 dark:hover:bg-indigo-600 text-white font-medium rounded-lg px-4 py-2"
              >
                {isRedirecting ? "Redirecting…" : "Continue to bank"}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
