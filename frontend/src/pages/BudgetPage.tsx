import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { budgetApi } from "../api/budget";
import type { BudgetCategoryRow, BudgetGroupRow, BudgetMonth, Scope } from "../api/types";
import { CoverOverspendingModal } from "../components/CoverOverspendingModal";
import { FundGoalsPreviewModal } from "../components/FundGoalsPreviewModal";
import { OverspentCategoriesModal } from "../components/OverspentCategoriesModal";
import { UnassignedTransactionsIsland } from "../components/UnassignedTransactionsIsland";
import { availablePillClass } from "../lib/budgetAvailability";
import { currentMonth, monthLabel, shiftMonth } from "../lib/dates";
import { formatGoal, monthlyGoalCents } from "../lib/goal";
import { formatCents, parseAmountToCents } from "../lib/money";
import { useScopes } from "../lib/useScopes";

const COLLAPSED_GROUPS_STORAGE_KEY = "budget:collapsed-groups";

// Shared column width/padding so the group header, category rows, and totals
// row all line up on desktop — matched by the categories table's colgroup
// (see TABLE_VALUE_COL_WIDTH below). Only enforced from `md:` up: below
// that, the header/totals rows fall back to gap-based flex spacing, exactly
// like before this column model existed — mobile only ever shows two of the
// four columns, so nothing to misalign there.
const VALUE_COL_WIDTH = "md:w-36"; // Goals / Assigned / Activity / Available
const VALUE_COL_PADDING = "md:px-5";

// The categories table stays table-fixed at every width (not just `md:`) so
// the name column can never push Assigned/Activity/Available past the
// card's `overflow-hidden` edge — auto layout has no guaranteed-space
// contract between columns, which is what let the Available pill get
// clipped below `md`. These reserve just enough room for the pill/values on
// a phone; the header/totals rows (flex, not table) don't need this since
// their value area is already `shrink-0` and never the one that overflows.
const TABLE_VALUE_COL_WIDTH = "w-28 md:w-36";
const TABLE_VALUE_COL_PADDING = "px-2 md:px-5";

const STEPPER_BUTTON_CLASS =
  "px-3 py-2 rounded-lg border border-stone-300 dark:border-stone-600 bg-white dark:bg-stone-900 hover:bg-stone-100 dark:hover:bg-stone-800";

const OVERSPENT_PILL_CLASS = "bg-red-100 text-red-900 dark:bg-red-900/40 dark:text-red-100";

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
  const [fundGoalsScopeId, setFundGoalsScopeId] = useState<number | null>(null);
  const [overspentScopeId, setOverspentScopeId] = useState<number | null>(null);
  const [coverCategoryId, setCoverCategoryId] = useState<number | null>(null);
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
    queryFn: () => budgetApi.get(month),
  });

  const assignMutation = useMutation({
    mutationFn: (vars: { categoryId: number; cents: number }) =>
      budgetApi.assign(month, vars.categoryId, vars.cents),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["budget"] });
    },
  });

  const fundGoalsPreviewQuery = useQuery({
    queryKey: ["budget", month, "fund-goals-preview", fundGoalsScopeId],
    queryFn: () => budgetApi.previewFundGoals(month, fundGoalsScopeId!),
    enabled: fundGoalsScopeId !== null,
  });

  const fundGoalsCommitMutation = useMutation({
    mutationFn: () => budgetApi.commitFundGoals(month, fundGoalsScopeId!),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["budget"] });
      setFundGoalsScopeId(null);
    },
  });

  const moveMoneyMutation = useMutation({
    mutationFn: (vars: { fromCategoryId: number; toCategoryId: number; amountCents: number }) =>
      budgetApi.moveMoney(month, vars.fromCategoryId, vars.toCategoryId, vars.amountCents),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["budget"] });
      setCoverCategoryId(null);
    },
  });

  const { scopes } = useScopes();
  const readyByScopeId = new Map(
    (budgetQuery.data?.ready_to_assign ?? []).map((row) => [
      row.scope_id,
      row.ready_to_assign_cents,
    ]),
  );
  const groupsByScopeId = new Map<number, BudgetGroupRow[]>();
  for (const group of budgetQuery.data?.groups ?? []) {
    groupsByScopeId.set(group.scope_id, [
      ...(groupsByScopeId.get(group.scope_id) ?? []),
      group,
    ]);
  }
  const neededCentsFor = (groups: BudgetGroupRow[]) =>
    groups
      .flatMap((g) => g.categories)
      .reduce((s, c) => s + (c.needed_this_month_cents ?? 0), 0);

  const allCategoriesFlat = (budgetQuery.data?.groups ?? []).flatMap((g) =>
    g.categories.map((c) => ({ ...c, groupName: g.name, scopeId: g.scope_id })),
  );

  const overspentCountByScopeId = new Map<number, number>();
  for (const c of allCategoriesFlat) {
    if (c.balance_cents < 0) {
      overspentCountByScopeId.set(c.scopeId, (overspentCountByScopeId.get(c.scopeId) ?? 0) + 1);
    }
  }

  const overspentCategoriesForModal = allCategoriesFlat
    .filter((c) => c.scopeId === overspentScopeId && c.balance_cents < 0)
    .map((c) => ({
      id: c.id,
      name: c.name,
      groupName: c.groupName,
      assignedCents: c.assigned_cents,
      balanceCents: c.balance_cents,
    }));

  const coverTargetCategory = allCategoriesFlat.find((c) => c.id === coverCategoryId);
  const coverTarget = coverTargetCategory
    ? { id: coverTargetCategory.id, name: coverTargetCategory.name, balanceCents: coverTargetCategory.balance_cents }
    : null;

  const coverSourceCandidates = coverTargetCategory
    ? allCategoriesFlat
        .filter(
          (c) =>
            c.scopeId === coverTargetCategory.scopeId &&
            c.id !== coverTargetCategory.id &&
            c.balance_cents > 0,
        )
        .map((c) => ({ id: c.id, name: c.name, groupName: c.groupName, balanceCents: c.balance_cents }))
    : [];

  return (
    <div className="max-w-4xl space-y-6">
      <header className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-2xl font-semibold">Budget</h1>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setMonth((m) => shiftMonth(m, -1))}
              className={STEPPER_BUTTON_CLASS}
            >
              ←
            </button>
            <div className="min-w-[8rem] text-center font-medium">{monthLabel(month)}</div>
            <button
              onClick={() => setMonth((m) => shiftMonth(m, 1))}
              className={STEPPER_BUTTON_CLASS}
            >
              →
            </button>
            {month !== currentMonth() && (
              <button
                onClick={() => setMonth(currentMonth())}
                className={`hidden md:inline-flex ${STEPPER_BUTTON_CLASS}`}
              >
                Today
              </button>
            )}
          </div>
        </div>
        {month !== currentMonth() && (
          <button
            onClick={() => setMonth(currentMonth())}
            className="md:hidden w-full py-1.5 rounded-lg border border-stone-300 dark:border-stone-600 bg-white dark:bg-stone-900 hover:bg-stone-100 dark:hover:bg-stone-800 text-sm font-medium"
          >
            Today
          </button>
        )}
      </header>

      <UnassignedTransactionsIsland />

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {scopes.map((scope) => {
          const overspentCount = overspentCountByScopeId.get(scope.id) ?? 0;
          return (
            <div key={scope.id} className="flex gap-4">
              <div className="flex-1">
                <ReadyToAssignPill
                  scope={scope}
                  cents={readyByScopeId.get(scope.id) ?? 0}
                  neededCents={neededCentsFor(groupsByScopeId.get(scope.id) ?? [])}
                />
              </div>
              {overspentCount > 0 && (
                <div className="flex-1">
                  <OverspentCategoriesPill
                    scope={scope}
                    count={overspentCount}
                    onClick={() => setOverspentScopeId(scope.id)}
                  />
                </div>
              )}
            </div>
          );
        })}
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

      {scopes.map((scope) => (
        <ScopeSection
          key={scope.id}
          scope={scope}
          groups={groupsByScopeId.get(scope.id) ?? []}
          collapsedGroups={collapsedGroups}
          toggleGroup={toggleGroup}
          onAssign={(categoryId, cents) => assignMutation.mutate({ categoryId, cents })}
          onFundGoals={() => setFundGoalsScopeId(scope.id)}
        />
      ))}

      <FundGoalsPreviewModal
        scopeName={scopes.find((s) => s.id === fundGoalsScopeId)?.name ?? ""}
        preview={fundGoalsPreviewQuery.data ?? null}
        isLoading={fundGoalsPreviewQuery.isLoading}
        isOpen={fundGoalsScopeId !== null}
        onClose={() => setFundGoalsScopeId(null)}
        onConfirm={() => fundGoalsCommitMutation.mutate()}
        isPending={fundGoalsCommitMutation.isPending}
        error={fundGoalsCommitMutation.isError ? "Failed to fund goals." : null}
      />

      <OverspentCategoriesModal
        scopeName={scopes.find((s) => s.id === overspentScopeId)?.name ?? ""}
        categories={overspentCategoriesForModal}
        isOpen={overspentScopeId !== null}
        onClose={() => {
          setOverspentScopeId(null);
          setCoverCategoryId(null);
        }}
        onSelectCategory={(categoryId) => setCoverCategoryId(categoryId)}
      />
      <CoverOverspendingModal
        targetCategory={coverTarget}
        sourceCandidates={coverSourceCandidates}
        isOpen={coverCategoryId !== null}
        onClose={() => setCoverCategoryId(null)}
        onConfirm={(sourceCategoryId, amountCents) =>
          moveMoneyMutation.mutate({
            fromCategoryId: sourceCategoryId,
            toCategoryId: coverCategoryId!,
            amountCents,
          })
        }
        isPending={moveMoneyMutation.isPending}
        error={
          moveMoneyMutation.isError
            ? "Couldn't move money — check the amount and try again."
            : null
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
        Ready to Assign — {scope.name}
      </div>
      <div className="text-3xl font-semibold tabular-nums">{formatCents(cents)}</div>
      <div className="text-xs mt-1 opacity-80 tabular-nums">Needed: {formatCents(neededCents)}</div>
    </div>
  );
}

function OverspentCategoriesPill({
  scope,
  count,
  onClick,
}: {
  scope: Scope;
  count: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`text-left w-full rounded-2xl p-5 ${OVERSPENT_PILL_CLASS}`}
    >
      <div className="text-xs uppercase tracking-wide opacity-70">Overspent — {scope.name}</div>
      <div className="text-3xl font-semibold tabular-nums">{count}</div>
      <div className="text-xs mt-1 opacity-80">
        {count === 1 ? "Overspent Category" : "Overspent Categories"}
      </div>
    </button>
  );
}

function ScopeSection({
  scope,
  groups,
  collapsedGroups,
  toggleGroup,
  onAssign,
  onFundGoals,
}: {
  scope: Scope;
  groups: BudgetGroupRow[];
  collapsedGroups: Set<number>;
  toggleGroup: (groupId: number) => void;
  onAssign: (categoryId: number, cents: number) => void;
  onFundGoals: () => void;
}) {
  const allCategories = groups.flatMap((g) => g.categories);
  const totalGoalCents = allCategories.reduce((s, c) => s + monthlyGoalCents(c), 0);
  const totalAssignedCents = allCategories.reduce((s, c) => s + c.assigned_cents, 0);
  const totalActivityCents = allCategories.reduce((s, c) => s + c.activity_cents, 0);
  const totalAvailableCents = allCategories.reduce((s, c) => s + c.balance_cents, 0);
  const totalNeededCents = allCategories.reduce(
    (s, c) => s + (c.needed_this_month_cents ?? 0),
    0,
  );

  return (
    <section className="space-y-3">
      <div
        className={`flex items-center justify-between rounded-xl px-4 py-2 ${scopeHeaderClass(totalAssignedCents, totalGoalCents)}`}
      >
        <h2 className="text-sm font-semibold uppercase tracking-wide">{scope.name}</h2>
        <div className="flex items-center gap-3">
          <span className="text-xs font-medium tabular-nums">
            Needed {formatCents(totalGoalCents)}/mo
          </span>
          {totalNeededCents > 0 && (
            <button
              type="button"
              onClick={onFundGoals}
              className="px-2 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold"
            >
              Fund goals
            </button>
          )}
        </div>
      </div>
      {groups.length === 0 ? (
        <div className="bg-white dark:bg-stone-900 border border-dashed border-stone-300 dark:border-stone-700 rounded-2xl p-6 text-center text-sm text-stone-500 dark:text-stone-400">
          No {scope.name} category groups yet. Add one on the{" "}
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
            const groupActivityCents = group.categories.reduce((s, c) => s + c.activity_cents, 0);
            return (
              <div
                key={group.id}
                className="bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 rounded-2xl overflow-hidden"
              >
                <button
                  type="button"
                  onClick={() => toggleGroup(group.id)}
                  aria-expanded={!isCollapsed}
                  className="w-full flex items-center gap-2 px-5 md:pl-5 md:pr-0 py-3 bg-stone-50 dark:bg-stone-800 border-b border-stone-200 dark:border-stone-700 text-sm font-semibold text-stone-700 dark:text-stone-200 hover:bg-stone-100 dark:hover:bg-stone-700/60 text-left"
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
                    <span className="block md:hidden truncate text-xs font-normal text-stone-400 dark:text-stone-500 tabular-nums">
                      {formatCents(groupMonthlyGoalCents)}/mo
                    </span>
                  </span>
                  <div className="flex gap-6 md:gap-0 shrink-0">
                    <div className={`hidden md:block text-right ${VALUE_COL_PADDING} ${VALUE_COL_WIDTH}`}>
                      <div className="text-xs font-normal text-stone-500 dark:text-stone-400 uppercase tracking-wide leading-none mb-0.5">
                        Goals/mo
                      </div>
                      <div className="tabular-nums">
                        {formatCents(groupMonthlyGoalCents)}
                      </div>
                    </div>
                    <div className={`text-right ${VALUE_COL_PADDING} ${VALUE_COL_WIDTH}`}>
                      <div className="text-xs font-normal text-stone-500 dark:text-stone-400 uppercase tracking-wide leading-none mb-0.5">
                        Assigned
                      </div>
                      <div className="tabular-nums">
                        {formatCents(
                          group.categories.reduce((s, c) => s + c.assigned_cents, 0),
                        )}
                      </div>
                    </div>
                    <div
                      className={`hidden landscape:block md:block text-right ${VALUE_COL_PADDING} ${VALUE_COL_WIDTH}`}
                    >
                      <div className="text-xs font-normal text-stone-500 dark:text-stone-400 uppercase tracking-wide leading-none mb-0.5">
                        Activity
                      </div>
                      <div className="tabular-nums">{formatCents(groupActivityCents)}</div>
                    </div>
                    <div className={`text-right ${VALUE_COL_PADDING} ${VALUE_COL_WIDTH}`}>
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
                      <table className="w-full text-sm table-fixed">
                        <colgroup>
                          <col />
                          <col className={`hidden md:table-column ${VALUE_COL_WIDTH}`} />
                          <col className={TABLE_VALUE_COL_WIDTH} />
                          <col className={`hidden landscape:table-column md:table-column ${TABLE_VALUE_COL_WIDTH}`} />
                          <col className={TABLE_VALUE_COL_WIDTH} />
                        </colgroup>
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
            totalActivityCents={totalActivityCents}
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
  totalActivityCents,
  totalAvailableCents,
}: {
  totalGoalCents: number;
  totalAssignedCents: number;
  totalActivityCents: number;
  totalAvailableCents: number;
}) {
  return (
    <div className="flex items-center gap-2 px-5 md:pl-5 md:pr-0 py-3 border-t-2 border-stone-300 dark:border-stone-600 text-sm font-semibold text-stone-700 dark:text-stone-200">
      <span className="flex-1 min-w-0">Total</span>
      <div className="flex gap-6 md:gap-0 shrink-0">
        <div className={`hidden md:block text-right ${VALUE_COL_PADDING} ${VALUE_COL_WIDTH}`}>
          <div className="text-xs font-normal text-stone-500 dark:text-stone-400 uppercase tracking-wide leading-none mb-0.5">
            Goals/mo
          </div>
          <div className="tabular-nums">{formatCents(totalGoalCents)}</div>
        </div>
        <div className={`text-right ${VALUE_COL_PADDING} ${VALUE_COL_WIDTH}`}>
          <div className="text-xs font-normal text-stone-500 dark:text-stone-400 uppercase tracking-wide leading-none mb-0.5">
            Assigned
          </div>
          <div className="tabular-nums">{formatCents(totalAssignedCents)}</div>
        </div>
        <div className={`hidden landscape:block md:block text-right ${VALUE_COL_PADDING} ${VALUE_COL_WIDTH}`}>
          <div className="text-xs font-normal text-stone-500 dark:text-stone-400 uppercase tracking-wide leading-none mb-0.5">
            Activity
          </div>
          <div className="tabular-nums">{formatCents(totalActivityCents)}</div>
        </div>
        <div className={`text-right ${VALUE_COL_PADDING} ${VALUE_COL_WIDTH}`}>
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
  const fallbackAssign = monthlyGoalCents(cat);
  return (
    <tr className="border-t border-stone-100 dark:border-stone-800">
      <td className="px-5 py-2">
        <div>{cat.name}</div>
        <div className="text-xs text-stone-500 dark:text-stone-400 flex items-center gap-2 flex-wrap">
          <span>{formatGoal(cat)}</span>
          {needed !== null && needed > 0 ? (
            <button
              type="button"
              onClick={() => onAssign(cat.assigned_cents + needed)}
              className="inline-block px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-800 dark:bg-indigo-900/50 dark:text-indigo-200 text-[10px] font-semibold tabular-nums hover:bg-indigo-200 dark:hover:bg-indigo-800/60 cursor-pointer"
              aria-label={`Assign ${formatCents(needed)} to reach this month's goal`}
            >
              Need {formatCents(needed)}
            </button>
          ) : (
            fallbackAssign > 0 && (
              <button
                type="button"
                onClick={() => onAssign(cat.assigned_cents + fallbackAssign)}
                className="inline-block px-1.5 py-0.5 rounded bg-stone-200 text-stone-700 dark:bg-stone-800 dark:text-stone-300 text-[10px] font-semibold tabular-nums hover:bg-stone-300 dark:hover:bg-stone-700 cursor-pointer"
                aria-label={`Assign this month's budget of ${formatCents(fallbackAssign)}`}
              >
                Assign {formatCents(fallbackAssign)}
              </button>
            )
          )}
        </div>
      </td>
      <td className="hidden md:table-cell" aria-hidden="true" />
      <td className={`${TABLE_VALUE_COL_PADDING} py-2 text-right tabular-nums whitespace-nowrap`}>
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
            className="w-20 md:w-28 text-right border border-indigo-300 dark:border-indigo-500 bg-transparent dark:bg-stone-900 rounded-md px-2 py-0.5 focus:outline-none focus:ring-2 focus:ring-indigo-500"
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
      <td
        className={`hidden landscape:table-cell md:table-cell ${TABLE_VALUE_COL_PADDING} py-2 text-right tabular-nums whitespace-nowrap text-stone-600 dark:text-stone-400`}
      >
        {formatCents(cat.activity_cents)}
      </td>
      <td className={`${TABLE_VALUE_COL_PADDING} py-2 text-right whitespace-nowrap`}>
        <span
          className={`inline-block px-2.5 py-1 rounded-full text-xs font-semibold tabular-nums ${availablePillClass(cat.assigned_cents, cat.balance_cents)}`}
        >
          {formatCents(cat.balance_cents)}
        </span>
      </td>
    </tr>
  );
}
