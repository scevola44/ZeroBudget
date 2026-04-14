import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { BudgetCategoryRow, BudgetMonth } from "../api/types";
import { currentMonth, monthLabel, shiftMonth } from "../lib/dates";
import { formatCents, parseAmountToCents } from "../lib/money";

export function BudgetPage() {
  const [month, setMonth] = useState<string>(currentMonth);
  const qc = useQueryClient();

  const budgetQuery = useQuery<BudgetMonth>({
    queryKey: ["budget", month],
    queryFn: () => api<BudgetMonth>(`/api/budget/${month}`),
  });

  const assignMutation = useMutation({
    mutationFn: (vars: { categoryId: number; cents: number }) =>
      api(`/api/budget/${month}/assign`, {
        method: "POST",
        body: { category_id: vars.categoryId, amount_cents: vars.cents },
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["budget"] });
    },
  });

  const ready = budgetQuery.data?.ready_to_assign_cents ?? 0;
  const readyColor =
    ready > 0 ? "bg-emerald-100 text-emerald-900" : ready < 0 ? "bg-red-100 text-red-900" : "bg-slate-100 text-slate-900";

  return (
    <div className="max-w-4xl space-y-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Budget</h1>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setMonth((m) => shiftMonth(m, -1))}
            className="px-3 py-1.5 rounded-lg border border-slate-300 bg-white hover:bg-slate-100"
          >
            ←
          </button>
          <div className="min-w-[10rem] text-center font-medium">{monthLabel(month)}</div>
          <button
            onClick={() => setMonth((m) => shiftMonth(m, 1))}
            className="px-3 py-1.5 rounded-lg border border-slate-300 bg-white hover:bg-slate-100"
          >
            →
          </button>
        </div>
      </header>

      <div className={`rounded-2xl p-5 ${readyColor}`}>
        <div className="text-xs uppercase tracking-wide opacity-70">Ready to Assign</div>
        <div className="text-3xl font-semibold tabular-nums">{formatCents(ready)}</div>
      </div>

      {budgetQuery.isLoading && <div className="text-slate-500">Loading budget…</div>}
      {budgetQuery.error && (
        <div className="text-red-600">Failed to load budget.</div>
      )}

      {budgetQuery.data && budgetQuery.data.groups.length === 0 && (
        <div className="bg-white border border-dashed border-slate-300 rounded-2xl p-8 text-center text-slate-600">
          No category groups yet. Create one on the{" "}
          <a className="text-indigo-600 hover:underline" href="/categories">
            Categories
          </a>{" "}
          page to start budgeting.
        </div>
      )}

      {budgetQuery.data?.groups.map((group) => (
        <section key={group.id} className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
          <header className="px-5 py-3 bg-slate-50 border-b border-slate-200 text-sm font-semibold text-slate-700">
            {group.name}
          </header>
          {group.categories.length === 0 ? (
            <div className="px-5 py-4 text-sm text-slate-500">No categories in this group.</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-xs uppercase text-slate-500">
                <tr>
                  <th className="text-left px-5 py-2">Category</th>
                  <th className="text-right px-5 py-2 w-40">Assigned</th>
                  <th className="text-right px-5 py-2 w-36">Activity</th>
                  <th className="text-right px-5 py-2 w-36">Available</th>
                </tr>
              </thead>
              <tbody>
                {group.categories.map((cat) => (
                  <CategoryRow
                    key={cat.id}
                    cat={cat}
                    onAssign={(cents) =>
                      assignMutation.mutate({ categoryId: cat.id, cents })
                    }
                  />
                ))}
              </tbody>
            </table>
          )}
        </section>
      ))}
    </div>
  );
}

function CategoryRow({
  cat,
  onAssign,
}: {
  cat: BudgetCategoryRow;
  onAssign: (cents: number) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(() => (cat.assigned_cents / 100).toFixed(2));

  function commit() {
    const cents = parseAmountToCents(draft);
    if (cents !== null && cents !== cat.assigned_cents) {
      onAssign(cents);
    }
    setEditing(false);
  }

  const balanceColor =
    cat.balance_cents > 0
      ? "text-emerald-700"
      : cat.balance_cents < 0
        ? "text-red-700"
        : "text-slate-700";

  return (
    <tr className="border-t border-slate-100">
      <td className="px-5 py-2">{cat.name}</td>
      <td className="px-5 py-2 text-right tabular-nums">
        {editing ? (
          <input
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === "Enter") commit();
              if (e.key === "Escape") setEditing(false);
            }}
            className="w-28 text-right border border-indigo-300 rounded-md px-2 py-0.5 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        ) : (
          <button
            className="hover:bg-slate-100 rounded px-2 py-0.5"
            onClick={() => {
              setDraft((cat.assigned_cents / 100).toFixed(2));
              setEditing(true);
            }}
          >
            {formatCents(cat.assigned_cents)}
          </button>
        )}
      </td>
      <td className="px-5 py-2 text-right tabular-nums text-slate-600">
        {formatCents(cat.activity_cents)}
      </td>
      <td className={`px-5 py-2 text-right tabular-nums font-medium ${balanceColor}`}>
        {formatCents(cat.balance_cents)}
      </td>
    </tr>
  );
}
