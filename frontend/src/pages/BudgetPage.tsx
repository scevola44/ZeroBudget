import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { BudgetCategoryRow, BudgetGroupRow, BudgetMonth, Scope } from "../api/types";
import { scopeLabel } from "../api/types";
import { currentMonth, monthLabel, shiftMonth } from "../lib/dates";
import { formatGoal, monthlyGoalCents } from "../lib/goal";
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

function readyToAssignBoxClass(readyCents: number, neededCents: number): string {
  if (readyCents < 0) return "bg-red-100 text-red-900 dark:bg-red-900/40 dark:text-red-100";
  if (neededCents > 0 && readyCents < neededCents)
    return "bg-red-100 text-red-900 dark:bg-red-900/40 dark:text-red-100";
  if (readyCents > 0)
    return "bg-emerald-100 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-100";
  return "bg-stone-200 text-stone-900 dark:bg-stone-800 dark:text-stone-100";
}

function scopeHeaderClass(assignedCents: number, goalCents: number): string {
  if (goalCents <= 0) return "bg-stone-100 text-stone-600 dark:bg-stone-800 dark:text-stone-300";
  if (assignedCents >= goalCents)
    return "bg-emerald-100 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-100";
  return "bg-red-100 text-red-900 dark:bg-red-900/40 dark:text-red-100";
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

  const personalReady = budgetQuery.data?.personal_ready_to_assign_cents ?? 0;
  const sharedReady = budgetQuery.data?.shared_ready_to_assign_cents ?? 0;
  const personalGroups: BudgetGroupRow[] =
    budgetQuery.data?.groups.filter((g) => g.scope === "personal") ?? [];
  const sharedGroups: BudgetGroupRow[] =
    budgetQuery.data?.groups.filter((g) => g.scope === "shared") ?? [];
  const personalNeededCents = personalGroups
    .flatMap((g) => g.categories)
    .reduce((s, c) => s + (c.needed_this_month_cents ?? 0), 0);
  const sharedNeededCents = sharedGroups
    .flatMap((g) => g.categories)
    .reduce((s, c) => s + (c.needed_this_month_cents ?? 0), 0);

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

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <ReadyToAssignPill scope="personal" cents={personalReady} neededCents={personalNeededCents} />
        <ReadyToAssignPill scope="shared" cents={sharedReady} neededCents={sharedNeededCents} />
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

      <ScopeSection
        scope="personal"
        groups={personalGroups}
        collapsedGroups={collapsedGroups}
        toggleGroup={toggleGroup}
        onAssign={(categoryId, cents) =>
          assignMutation.mutate({ categoryId, cents })
        }
      />
      <ScopeSection
        scope="shared"
        groups={sharedGroups}
        collapsedGroups={collapsedGroups}
        toggleGroup={toggleGroup}
        onAssign={(categoryId, cents) =>
          assignMutation.mutate({ categoryId, cents })
        }
      />
    </div>
  );
}

function ReadyToAssignPill({
  scope,
  cents,
  neededCents,
}: {
  scope: Scope;
  cents: number;
  neededCents: number;
}) {
  return (
    <div className={`rounded-2xl p-5 ${readyToAssignBoxClass(cents, neededCents)}`}>
      <div className="text-xs uppercase tracking-wide opacity-70">
        Ready to Assign — {scopeLabel(scope)}
      </div>
      <div className="text-3xl font-semibold tabular-nums">{formatCents(cents)}</div>
      <div className="text-xs mt-1 opacity-80 tabular-nums">Needed: {formatCents(neededCents)}</div>
    </div>
  );
}

function ScopeSection({
  scope,
  groups,
  collapsedGroups,
  toggleGroup,
  onAssign,
}: {
  scope: Scope;
  groups: BudgetGroupRow[];
  collapsedGroups: Set<number>;
  toggleGroup: (groupId: number) => void;
  onAssign: (categoryId: number, cents: number) => void;
}) {
  const allCategories = groups.flatMap((g) => g.categories);
  const totalGoalCents = allCategories.reduce((s, c) => s + monthlyGoalCents(c), 0);
  const totalAssignedCents = allCategories.reduce((s, c) => s + c.assigned_cents, 0);
  const totalAvailableCents = allCategories.reduce((s, c) => s + c.balance_cents, 0);

  return (
    <section className="space-y-3">
      <div
        className={`flex items-center justify-between rounded-xl px-4 py-2 ${scopeHeaderClass(totalAssignedCents, totalGoalCents)}`}
      >
        <h2 className="text-sm font-semibold uppercase tracking-wide">{scopeLabel(scope)}</h2>
        <span className="text-xs font-medium tabular-nums">
          Needed {formatCents(totalGoalCents)}/mo
        </span>
      </div>
      {groups.length === 0 ? (
        <div className="bg-white dark:bg-stone-900 border border-dashed border-stone-300 dark:border-stone-700 rounded-2xl p-6 text-center text-sm text-stone-500 dark:text-stone-400">
          No {scopeLabel(scope).toLowerCase()} category groups yet. Add one on the{" "}
          <a className="text-indigo-600 dark:text-indigo-400 hover:underline" href="/categories">
            Categories
          </a>{" "}
          page.
        </div>
      ) : (
        <>
          {groups.map((group) => {
            const isCollapsed = collapsedGroups.has(group.id);
            const groupMonthlyGoalCents = group.categories.reduce((s, c) => s + monthlyGoalCents(c), 0);
            return (
              <div
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
                    className={`w-4 h-4 shrink-0 transition-transform ${isCollapsed ? "-rotate-90" : ""}`}
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
                  <span className="flex-1 min-w-0">
                    <span className="block truncate">{group.name}</span>
                    <span className="block md:hidden text-xs font-normal text-stone-400 dark:text-stone-500 tabular-nums">
                      {formatCents(groupMonthlyGoalCents)}/mo
                    </span>
                  </span>
                  <div className="flex gap-6 shrink-0">
                    <div className="hidden md:block text-right">
                      <div className="text-xs font-normal text-stone-500 dark:text-stone-400 uppercase tracking-wide leading-none mb-0.5">
                        Goals/mo
                      </div>
                      <div className="tabular-nums">
                        {formatCents(groupMonthlyGoalCents)}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs font-normal text-stone-500 dark:text-stone-400 uppercase tracking-wide leading-none mb-0.5">
                        Assigned
                      </div>
                      <div className="tabular-nums">
                        {formatCents(
                          group.categories.reduce((s, c) => s + c.assigned_cents, 0),
                        )}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs font-normal text-stone-500 dark:text-stone-400 uppercase tracking-wide leading-none mb-0.5">
                        Available
                      </div>
                      <div className="tabular-nums">
                        {formatCents(
                          group.categories.reduce((s, c) => s + c.balance_cents, 0),
                        )}
                      </div>
                    </div>
                  </div>
                </button>
                {!isCollapsed &&
                  (group.categories.length === 0 ? (
                    <div className="px-5 py-4 text-sm text-stone-500 dark:text-stone-400">
                      No categories in this group.
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <tbody>
                          {group.categories.map((cat) => (
                            <CategoryRow
                              key={cat.id}
                              cat={cat}
                              onAssign={(cents) => onAssign(cat.id, cents)}
                            />
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ))}
              </div>
            );
          })}
          <SectionTotalsRow
            totalGoalCents={totalGoalCents}
            totalAssignedCents={totalAssignedCents}
            totalAvailableCents={totalAvailableCents}
          />
        </>
      )}
    </section>
  );
}

function SectionTotalsRow({
  totalGoalCents,
  totalAssignedCents,
  totalAvailableCents,
}: {
  totalGoalCents: number;
  totalAssignedCents: number;
  totalAvailableCents: number;
}) {
  return (
    <div className="flex items-center gap-2 px-5 py-3 border-t-2 border-stone-300 dark:border-stone-600 text-sm font-semibold text-stone-700 dark:text-stone-200">
      <span className="flex-1 min-w-0">Total</span>
      <div className="flex gap-6 shrink-0">
        <div className="hidden md:block text-right min-w-[5rem]">
          <div className="text-xs font-normal text-stone-500 dark:text-stone-400 uppercase tracking-wide leading-none mb-0.5">
            Goals/mo
          </div>
          <div className="tabular-nums">{formatCents(totalGoalCents)}</div>
        </div>
        <div className="text-right min-w-[5rem]">
          <div className="text-xs font-normal text-stone-500 dark:text-stone-400 uppercase tracking-wide leading-none mb-0.5">
            Assigned
          </div>
          <div className="tabular-nums">{formatCents(totalAssignedCents)}</div>
        </div>
        <div className="text-right min-w-[5rem]">
          <div className="text-xs font-normal text-stone-500 dark:text-stone-400 uppercase tracking-wide leading-none mb-0.5">
            Available
          </div>
          <div className="tabular-nums">{formatCents(totalAvailableCents)}</div>
        </div>
      </div>
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

  const needed = cat.needed_this_month_cents;
  return (
    <tr className="border-t border-stone-100 dark:border-stone-800">
      <td className="px-5 py-2">
        <div>{cat.name}</div>
        <div className="text-xs text-stone-500 dark:text-stone-400 flex items-center gap-2">
          <span>{formatGoal(cat)}</span>
          {needed !== null && needed > 0 && (
            <button
              type="button"
              onClick={() => onAssign(cat.assigned_cents + needed)}
              className="inline-block px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-800 dark:bg-indigo-900/50 dark:text-indigo-200 text-[10px] font-semibold tabular-nums hover:bg-indigo-200 dark:hover:bg-indigo-800/60 cursor-pointer"
              aria-label={`Assign ${formatCents(needed)} to reach this month's goal`}
            >
              Need {formatCents(needed)}
            </button>
          )}
        </div>
      </td>
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
            inputMode="decimal"
            className="w-28 text-right border border-indigo-300 dark:border-indigo-500 bg-transparent dark:bg-stone-900 rounded-md px-2 py-0.5 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        ) : (
          <button
            className="hover:bg-stone-100 dark:hover:bg-stone-800 rounded px-2 py-0.5"
            onClick={() => {
              setDraft("");
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
