import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { api } from "../api/client";

/**
 * All-time count of transactions that still need a category — not just
 * within whatever date range the current page happens to be showing, so a
 * row left unassigned from a past month doesn't go unnoticed. Shares the
 * "transactions" query-key prefix with TransactionsPage's own queries so its
 * existing invalidations (after import, edit, transfer-link, unlink) also
 * refresh this count for free.
 */
export function UnassignedTransactionsIsland() {
  const navigate = useNavigate();

  const countQuery = useQuery<{ count: number }>({
    queryKey: ["transactions", "unassigned-count"],
    queryFn: () => api<{ count: number }>("/api/transactions/unassigned-count"),
  });

  const count = countQuery.data?.count ?? 0;
  if (count === 0) return null;

  return (
    <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/50 rounded-2xl px-5 py-4 flex items-center justify-between gap-4">
      <span className="text-sm font-medium text-amber-900 dark:text-amber-200">
        {count} transaction{count === 1 ? "" : "s"} need{count === 1 ? "s" : ""} a category
      </span>
      <button
        type="button"
        onClick={() => navigate("/transactions?filter=unassigned")}
        className="bg-amber-600 hover:bg-amber-700 dark:bg-amber-500 dark:hover:bg-amber-600 text-white rounded-lg px-3 py-1.5 text-sm font-medium whitespace-nowrap"
      >
        Review →
      </button>
    </div>
  );
}
