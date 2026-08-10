import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { Account, Transaction, TransferSuggestion } from "../api/types";
import { formatCents } from "../lib/money";

/**
 * Pairs of imported rows that look like the two halves of one transfer.
 *
 * A bank sync fetches each account separately, so it can't know that the money
 * leaving one account is the money arriving in another. Until the two rows are
 * linked they read as real income and real spending on Insights — but a €50
 * refund and an unrelated €50 purchase look identical to a matcher, so every
 * pair is only ever offered, never linked automatically.
 */
export function TransferSuggestionsBanner({
  startDate,
  endDate,
  accountById,
  onLinked,
}: {
  startDate: string;
  endDate: string;
  accountById: Record<number, Account | undefined>;
  onLinked: () => void;
}) {
  const qc = useQueryClient();

  const suggestionsQuery = useQuery<TransferSuggestion[]>({
    queryKey: ["transfer-suggestions", startDate, endDate],
    queryFn: () =>
      api<TransferSuggestion[]>(
        `/api/transactions/transfer-suggestions?start_date=${startDate}&end_date=${endDate}`,
      ),
  });

  const link = useMutation({
    mutationFn: (pair: TransferSuggestion) =>
      api(`/api/transactions/${pair.outflow.id}/transfer-link`, {
        method: "POST",
        body: { peer_transaction_id: pair.inflow.id },
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["transfer-suggestions"] });
      onLinked();
    },
  });

  const linkAll = useMutation({
    // Suggestions are disjoint by construction, so linking them in sequence
    // never invalidates a later pair.
    mutationFn: async (pairs: TransferSuggestion[]) => {
      for (const pair of pairs) {
        await api(`/api/transactions/${pair.outflow.id}/transfer-link`, {
          method: "POST",
          body: { peer_transaction_id: pair.inflow.id },
        });
      }
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["transfer-suggestions"] });
      onLinked();
    },
  });

  const suggestions = suggestionsQuery.data ?? [];
  if (suggestions.length === 0) return null;

  const isPending = link.isPending || linkAll.isPending;
  const error = link.error ?? linkAll.error;

  function accountName(txn: Transaction): string {
    return accountById[txn.account_id]?.name ?? "another account";
  }

  return (
    <div className="bg-indigo-50 dark:bg-indigo-950/30 border border-indigo-200 dark:border-indigo-900/50 rounded-2xl p-5 space-y-3">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-semibold text-indigo-900 dark:text-indigo-200">
            Possible transfers
          </h2>
          <p className="text-sm text-indigo-800/80 dark:text-indigo-300/80">
            These pairs look like money moving between your own accounts. Linking one
            keeps it out of income and spending.
          </p>
        </div>
        {suggestions.length > 1 && (
          <button
            type="button"
            disabled={isPending}
            onClick={() => linkAll.mutate(suggestions)}
            className="bg-indigo-600 hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600 disabled:opacity-50 text-white rounded-lg px-3 py-1.5 text-sm font-medium whitespace-nowrap"
          >
            {linkAll.isPending ? "Linking…" : "Link all"}
          </button>
        )}
      </div>

      <ul className="space-y-2">
        {suggestions.map((pair) => (
          <li
            key={`${pair.outflow.id}-${pair.inflow.id}`}
            className="bg-white dark:bg-stone-900 border border-indigo-100 dark:border-stone-700 rounded-lg px-4 py-3 flex items-center justify-between gap-4"
          >
            <div className="min-w-0 text-sm">
              <div className="truncate text-stone-800 dark:text-stone-200">
                {accountName(pair.outflow)} → {accountName(pair.inflow)}
              </div>
              <div className="text-xs text-stone-500 dark:text-stone-400">
                {pair.outflow.date}
                {pair.inflow.date !== pair.outflow.date && ` → ${pair.inflow.date}`}
                {pair.outflow.payee && ` · ${pair.outflow.payee}`}
              </div>
            </div>
            <div className="flex items-center gap-3 whitespace-nowrap">
              <span className="tabular-nums text-sm text-stone-900 dark:text-stone-100">
                {formatCents(Math.abs(pair.outflow.amount_cents))}
              </span>
              <button
                type="button"
                disabled={isPending}
                onClick={() => link.mutate(pair)}
                className="border border-indigo-300 dark:border-indigo-600 text-indigo-700 dark:text-indigo-300 hover:bg-indigo-50 dark:hover:bg-indigo-900/40 disabled:opacity-50 rounded-lg px-3 py-1 text-sm"
              >
                Link
              </button>
            </div>
          </li>
        ))}
      </ul>

      {error && (
        <p className="text-sm text-red-600 dark:text-red-400">
          {error instanceof Error ? error.message : "Could not link the transfer"}
        </p>
      )}
    </div>
  );
}
