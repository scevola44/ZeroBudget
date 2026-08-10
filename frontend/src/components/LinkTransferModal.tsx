import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { Account, Transaction, TransferCandidate } from "../api/types";
import { formatCents } from "../lib/money";

function offsetLabel(days: number): string {
  if (days === 0) return "same day";
  const magnitude = Math.abs(days);
  const unit = magnitude === 1 ? "day" : "days";
  return days < 0 ? `${magnitude} ${unit} earlier` : `${magnitude} ${unit} later`;
}

/**
 * Pick which transaction in `targetAccount` is the other leg of `transaction`.
 *
 * A bank sync writes each account's side of a transfer independently, so both
 * rows already exist and only the link is missing. Nothing is ever created here:
 * if the other side isn't in ZeroBudget, there is nothing to link and the
 * add-transaction form is the right tool instead.
 */
export function LinkTransferModal({
  transaction,
  targetAccount,
  onClose,
  onLinked,
}: {
  transaction: Transaction;
  targetAccount: Account;
  onClose: () => void;
  onLinked: () => void;
}) {
  const qc = useQueryClient();

  const candidatesQuery = useQuery<TransferCandidate[]>({
    queryKey: ["transfer-candidates", transaction.id, targetAccount.id],
    queryFn: () =>
      api<TransferCandidate[]>(
        `/api/transactions/transfer-candidates?transaction_id=${transaction.id}` +
          `&account_id=${targetAccount.id}`,
      ),
  });

  const link = useMutation({
    mutationFn: (peerId: number) =>
      api(`/api/transactions/${transaction.id}/transfer-link`, {
        method: "POST",
        body: { peer_transaction_id: peerId },
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["transfer-suggestions"] });
      onLinked();
    },
  });

  const candidates = candidatesQuery.data ?? [];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-white dark:bg-stone-900 rounded-2xl shadow-xl w-full max-w-lg">
        <div className="flex items-center justify-between px-6 py-4 border-b border-stone-200 dark:border-stone-700">
          <h2 className="text-lg font-semibold">Link as transfer</h2>
          <button
            type="button"
            onClick={onClose}
            disabled={link.isPending}
            className="text-stone-500 hover:text-stone-800 dark:hover:text-stone-200 text-xl leading-none disabled:opacity-50"
          >
            ✕
          </button>
        </div>

        <div className="p-6 space-y-4">
          <p className="text-sm text-stone-600 dark:text-stone-400">
            Which transaction in{" "}
            <span className="font-medium text-stone-800 dark:text-stone-200">
              {targetAccount.name}
            </span>{" "}
            is the other half of{" "}
            <span className="tabular-nums font-medium text-stone-800 dark:text-stone-200">
              {formatCents(transaction.amount_cents)}
            </span>{" "}
            on {transaction.date}?
          </p>

          {candidatesQuery.isPending && (
            <p className="text-sm text-stone-500 dark:text-stone-400">Looking…</p>
          )}

          {candidatesQuery.isSuccess && candidates.length === 0 && (
            <div className="bg-stone-50 dark:bg-stone-800 border border-stone-200 dark:border-stone-700 rounded-lg px-4 py-3 text-sm text-stone-600 dark:text-stone-400">
              <p>
                Nothing in {targetAccount.name} matches this amount within a few days.
              </p>
              <p className="mt-2">
                Both halves have to already exist to be linked. If the other side was
                never imported, add it with the transaction form and pick{" "}
                <span className="whitespace-nowrap">Transfer : {targetAccount.name}</span>{" "}
                there — that creates both legs at once.
              </p>
            </div>
          )}

          {candidates.length > 0 && (
            <ul className="divide-y divide-stone-100 dark:divide-stone-800 border border-stone-200 dark:border-stone-700 rounded-lg overflow-hidden">
              {candidates.map(({ transaction: candidate, date_offset_days }) => (
                <li key={candidate.id}>
                  <button
                    type="button"
                    disabled={link.isPending}
                    onClick={() => link.mutate(candidate.id)}
                    className="w-full text-left px-4 py-3 hover:bg-stone-50 dark:hover:bg-stone-800 disabled:opacity-50 flex items-center justify-between gap-3"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm text-stone-800 dark:text-stone-200">
                        {candidate.payee || "—"}
                      </span>
                      <span className="block text-xs text-stone-500 dark:text-stone-400">
                        {candidate.date} · {offsetLabel(date_offset_days)}
                      </span>
                    </span>
                    <span className="tabular-nums text-sm text-stone-900 dark:text-stone-100 whitespace-nowrap">
                      {formatCents(candidate.amount_cents)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {candidates.some((c) => c.transaction.category_id !== null) && (
            <p className="text-xs text-stone-500 dark:text-stone-400">
              Linking clears any category on both rows — a transfer isn't spending.
            </p>
          )}

          {link.isError && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/50 rounded-lg px-3 py-2 text-sm text-red-800 dark:text-red-200">
              {link.error instanceof Error ? link.error.message : "Could not link"}
            </div>
          )}

          {candidatesQuery.isError && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/50 rounded-lg px-3 py-2 text-sm text-red-800 dark:text-red-200">
              Could not load matching transactions.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
