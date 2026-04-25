import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { BudgetCategoryRow, BudgetMonth } from "../api/types";
import { currentMonth, monthLabel, shiftMonth } from "../lib/dates";
import { formatCents, parseAmountToCents } from "../lib/money";

const COLLAPSED_GROUPS_STORAGE_KEY = "budget:collapsed-groups";

function loadCollapsedGroups(): Set<number> {
  try {
    const raw = localStorage.getItem(COLLAPSED_GROUPS_STORAGE_KEY);
    if (!raw) return new Set();
    const ids = JSON.parse(raw) as unknown;
    if (!Array.isArray(ids)) return new Set();
    return new Set(ids.filter((v): v is number => typeof v === "number"));
  } catch {
    return new Set();
  }
}

function availablePillClass(assignedCents: number, balanceCents: number): string {
  if (balanceCents < 0) {
    return "bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-200";
  }
  if (assignedCents === 0) {
    return "bg-stone-200 text-stone-600 dark:bg-stone-800 dark:text-stone-300";
  }
  if (balanceCents >= assignedCents) {
    return "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-200";
  }
  return "bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200";
}

export function BudgetPage() {
  const [month, setMonth] = useState<string>(currentMonth);
  const [collapsedGroups, setCollapsedGroups] = useState<Set<number>>(loadCollapsedGroups);
  const qc = useQueryClient();

  useEffect(() => {
    localStorage.setItem(
      COLLAPSED_GROUPS_STORAGE_KEY,
      JSON.stringify([...collapsedGroups]),
    );
  }, [collapsedGroups]);

  function toggleGroup(groupId: number) {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
  }

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
    ready > 0
      ? "bg-emerald-100 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-100"
      : ready < 0
        ? "bg-red-100 text-red-900 dark:bg-red-900/40 dark:text-red-100"
        : "bg-stone-200 text-stone-900 dark:bg-stone-800 dark:text-stone-100";

  return (
    <div className="max-w-4xl space-y-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Budget</h1>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setMonth((m) => shiftMonth(m, -1))}
            className="px-3 py-2 rounded-lg border border-stone-300 dark:border-stone-600 bg-white dark:bg-stone-900 hover:bg-stone-100 dark:hover:bg-stone-800"
          >
            ←
          </button>
          <div className="min-w-[8rem] text-center font-medium">{monthLabel(month)}</div>
          <button
            onClick={() => setMonth((m) => shiftMonth(m, 1))}
            className="px-3 py-2 rounded-lg border border-stone-300 dark:border-stone-600 bg-white dark:bg-stone-900 hover:bg-stone-100 dark:hover:bg-stone-800"
          >
            →
          </button>
        </div>
      </header>

      <div className={`rounded-2xl p-5 ${readyColor}`}>
        <div className="text-xs uppercase tracking-wide opacity-70">Ready to Assign</div>
        <div className="text-3xl font-semibold tabular-nums">{formatCents(ready)}</div>
      </div>

      {budgetQuery.isLoading && (
        <div className="text-stone-500 dark:text-stone-400">Loading budget…</div>
      )}
      {budgetQuery.error && (
        <div className="text-red-600 dark:text-red-400">Failed to load budget.</div>
      )}

      {budgetQuery.data && budgetQuery.data.groups.length === 0 && (
        <div className="bg-white dark:bg-stone-900 border border-dashed border-stone-300 dark:border-stone-700 rounded-2xl p-8 text-center text-stone-600 dark:text-stone-400">
          No category groups yet. Create one on the{" "}
          <a className="text-indigo-600 dark:text-indigo-400 hover:underline" href="/categories">
            Categories
          </a>{" "}
          page to start budgeting.
        </div>
      )}

      {budgetQuery.data?.groups.map((group) => {
        const isCollapsed = collapsedGroups.has(group.id);
        return (
          <section
            key={group.id}
            className="bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 rounded-2xl overflow-hidden"
          >
            <button
              type="button"
              onClick={() => toggleGroup(group.id)}
              aria-expanded={!isCollapsed}
              className="w-full flex items-center gap-2 px-5 py-3 bg-stone-50 dark:bg-stone-800 border-b border-stone-200 dark:border-stone-700 text-sm font-semibold text-stone-700 dark:text-stone-200 hover:bg-stone-100 dark:hover:bg-stone-700/60 text-left"
            >
              <svg
                className={`w-4 h-4 transition-transform ${isCollapsed ? "-rotate-90" : ""}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 9l-7 7-7-7"
                />
              </svg>
              <span>{group.name}</span>
            </button>
            {!isCollapsed && (
              group.categories.length === 0 ? (
                <div className="px-5 py-4 text-sm text-stone-500 dark:text-stone-400">
                  No categories in this group.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="text-xs uppercase text-stone-500 dark:text-stone-400">
                      <tr>
                        <th className="text-left px-5 py-2">Category</th>
                        <th className="text-right px-5 py-2 w-32 md:w-40">Assigned</th>
                        <th className="hidden landscape:table-cell md:table-cell text-right px-5 py-2 w-36">
                          Activity
                        </th>
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
                </div>
              )
            )}
          </section>
        );
      })}
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

  return (
    <tr className="border-t border-stone-100 dark:border-stone-800">
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
            className="w-28 text-right border border-indigo-300 dark:border-indigo-500 bg-transparent dark:bg-stone-900 rounded-md px-2 py-0.5 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        ) : (
          <button
            className="hover:bg-stone-100 dark:hover:bg-stone-800 rounded px-2 py-0.5"
            onClick={() => {
              setDraft((cat.assigned_cents / 100).toFixed(2));
              setEditing(true);
            }}
          >
            {formatCents(cat.assigned_cents)}
          </button>
        )}
      </td>
      <td className="hidden landscape:table-cell md:table-cell px-5 py-2 text-right tabular-nums text-stone-600 dark:text-stone-400">
        {formatCents(cat.activity_cents)}
      </td>
      <td className="px-5 py-2 text-right">
        <span
          className={`inline-block px-2.5 py-1 rounded-full text-xs font-semibold tabular-nums ${availablePillClass(cat.assigned_cents, cat.balance_cents)}`}
        >
          {formatCents(cat.balance_cents)}
        </span>
      </td>
    </tr>
  );
}
