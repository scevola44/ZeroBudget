import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import type {
  CategoryTrendRow,
  Insights,
  ScopeBreakdown,
  ScopeFlow,
  ScopeOverspending,
  ScopeSplitRow,
} from "../api/types";

import { ScopeChip } from "../components/ScopeChip";
import { OTHER_SERIES_CLASS, seriesClass } from "../lib/chartColors";
import { scopeBarClass } from "../lib/scopeColors";
import { useScopes } from "../lib/useScopes";
import { currentMonth, monthLabel, shiftMonth } from "../lib/dates";
import type { RangePreset } from "../lib/insightsRange";
import {
  RANGE_PRESETS,
  monthsInPreset,
  rangeLabel,
  resolveRange,
  shortMonthLabel,
} from "../lib/insightsRange";
import { formatCents } from "../lib/money";

const CARD_CLASS =
  "bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 rounded-2xl";
const EMPTY_CARD_CLASS =
  "bg-white dark:bg-stone-900 border border-dashed border-stone-300 dark:border-stone-700 rounded-2xl p-8 text-center text-stone-500 dark:text-stone-400";
const STEPPER_BUTTON_CLASS =
  "px-3 py-2 rounded-lg border border-stone-300 dark:border-stone-600 bg-white dark:bg-stone-900 hover:bg-stone-100 dark:hover:bg-stone-800";
const SECTION_HEADING_CLASS = "text-lg font-semibold";
const MUTED_CLASS = "text-stone-500 dark:text-stone-400";
// Only the leading groups are named on the bar itself; the legend below carries
// the rest. Past this the labels collide on a phone.
const DIRECT_LABEL_COUNT = 4;
// Above this a spending overshoot stops being "a bit more" and reads as a
// problem, so the pill turns red rather than amber.
const SEVERE_OVERSHOOT_PCT = 25;

export function InsightsPage() {
  const [preset, setPreset] = useState<RangePreset>("1M");
  const [anchorMonth, setAnchorMonth] = useState<string>(currentMonth);
  const { startMonth, endMonth } = resolveRange(preset, anchorMonth);

  const insightsQuery = useQuery<Insights>({
    queryKey: ["insights", startMonth, endMonth],
    queryFn: () =>
      api<Insights>(`/api/insights?start_month=${startMonth}&end_month=${endMonth}`),
    // Stepping through months shouldn't blank the page between requests.
    placeholderData: keepPreviousData,
  });

  const insights = insightsQuery.data;

  return (
    <div className="max-w-5xl space-y-8">
      <header className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-2xl font-semibold">Insights</h1>
          <PresetPicker preset={preset} onChange={setPreset} anchorMonth={anchorMonth} />
        </div>
        <div className="flex items-center gap-2">
          <button
            className={STEPPER_BUTTON_CLASS}
            onClick={() => setAnchorMonth((month) => shiftMonth(month, -1))}
            aria-label="Previous month"
          >
            ←
          </button>
          <div className="min-w-[12rem] text-center font-medium">
            {rangeLabel(startMonth, endMonth)}
          </div>
          <button
            className={STEPPER_BUTTON_CLASS}
            onClick={() => setAnchorMonth((month) => shiftMonth(month, 1))}
            aria-label="Next month"
          >
            →
          </button>
        </div>
      </header>

      {insightsQuery.isLoading && <div className={MUTED_CLASS}>Loading insights…</div>}
      {insightsQuery.error && (
        <div className="text-red-600 dark:text-red-400">Failed to load insights.</div>
      )}

      {insights && (
        <>
          <SpendingSection insights={insights} />
          <IncomeVsSpendingSection insights={insights} />
          <OverspendingSection insights={insights} />
        </>
      )}
    </div>
  );
}

function PresetPicker({
  preset,
  anchorMonth,
  onChange,
}: {
  preset: RangePreset;
  anchorMonth: string;
  onChange: (preset: RangePreset) => void;
}) {
  return (
    <div className="flex items-center gap-1 rounded-lg bg-stone-100 dark:bg-stone-800 p-1">
      {RANGE_PRESETS.map((option) => (
        <button
          key={option}
          onClick={() => onChange(option)}
          aria-pressed={option === preset}
          title={`${monthsInPreset(option, anchorMonth)} months ending ${monthLabel(anchorMonth)}`}
          className={`px-3 py-1 rounded-md text-sm font-medium ${
            option === preset
              ? "bg-indigo-600 dark:bg-indigo-500 text-white"
              : "text-stone-600 dark:text-stone-300 hover:bg-stone-200 dark:hover:bg-stone-700"
          }`}
        >
          {option}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Where the money went
// ---------------------------------------------------------------------------

function SpendingSection({ insights }: { insights: Insights }) {
  const { scope_split: split, scopes } = insights.breakdown;

  return (
    <section className="space-y-4">
      <h2 className={SECTION_HEADING_CLASS}>Where the money went</h2>
      <ScopeSplitBar rows={split.scopes} totalCents={split.total_spent_cents} />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {scopes.map((breakdown) => (
          <ScopeSpendingCard key={breakdown.scope_id} breakdown={breakdown} />
        ))}
      </div>
    </section>
  );
}

function ScopeSplitBar({
  rows,
  totalCents,
}: {
  rows: ScopeSplitRow[];
  totalCents: number;
}) {
  const { scopeById } = useScopes();

  if (totalCents <= 0) {
    return <div className={EMPTY_CARD_CLASS}>No spending in this range.</div>;
  }

  // A zero-width segment still contributes a visible gap in a `gap-0.5` flex
  // row, so scopes with no spending are dropped from the bar. They keep their
  // legend entry: a zero there is informative where a zero sliver is just noise.
  const segments = rows.filter((row) => row.spent_cents > 0);

  return (
    <div className={`${CARD_CLASS} p-5 space-y-3`}>
      <div className={`text-xs uppercase tracking-wide ${MUTED_CLASS}`}>
        Split by scope
      </div>
      <div className="flex gap-0.5 h-3 w-full">
        {segments.map((row, index) => (
          <div
            key={row.scope_id}
            className={[
              scopeBarClass(scopeById.get(row.scope_id)?.sort_order ?? index),
              index === 0 ? "rounded-l-full" : "",
              index === segments.length - 1 ? "rounded-r-full" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            style={{ width: `${percentOf(row.spent_cents, totalCents)}%` }}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
        {rows.map((row) => (
          <SplitLegendEntry
            key={row.scope_id}
            scopeId={row.scope_id}
            cents={row.spent_cents}
            totalCents={totalCents}
          />
        ))}
      </div>
    </div>
  );
}

function SplitLegendEntry({
  scopeId,
  cents,
  totalCents,
}: {
  scopeId: number;
  cents: number;
  totalCents: number;
}) {
  return (
    <span className="flex items-center gap-2">
      <ScopeChip scopeId={scopeId} />
      <span className="tabular-nums">
        {formatCents(cents)} · {formatPercent(percentOf(cents, totalCents))}
      </span>
    </span>
  );
}

function ScopeSpendingCard({ breakdown }: { breakdown: ScopeBreakdown }) {
  const spentGroups = breakdown.groups.filter((group) => group.spent_cents > 0);
  const total = breakdown.total_spent_cents;
  const largestCategoryCents = Math.max(
    ...breakdown.categories.map((category) => category.spent_cents),
    1,
  );

  return (
    <div className={CARD_CLASS}>
      <div className="px-5 py-3 border-b border-stone-200 dark:border-stone-700 flex items-center justify-between gap-3">
        <ScopeChip scopeId={breakdown.scope_id} />
        <span className="font-semibold tabular-nums">{formatCents(total)}</span>
      </div>

      {total <= 0 ? (
        <div className={`px-5 py-8 text-center ${MUTED_CLASS}`}>
          Nothing spent in this scope this range.
        </div>
      ) : (
        <div className="p-5 space-y-5">
          <div className="space-y-3">
            <div className="flex gap-0.5 h-3 w-full">
              {spentGroups.map((group) => (
                <div
                  key={group.group_id}
                  className={`${seriesClass(group.sort_index)} first:rounded-l-full last:rounded-r-full`}
                  style={{ width: `${percentOf(group.spent_cents, total)}%` }}
                  title={`${group.name} · ${formatCents(group.spent_cents)}`}
                />
              ))}
            </div>
            <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
              {spentGroups.map((group, rank) => (
                <li key={group.group_id} className="flex items-center gap-2">
                  <span
                    className={`inline-block w-2.5 h-2.5 rounded-sm ${seriesClass(group.sort_index)}`}
                  />
                  <span>{group.name}</span>
                  {rank < DIRECT_LABEL_COUNT && (
                    <span className={`tabular-nums ${MUTED_CLASS}`}>
                      {formatCents(group.spent_cents)}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </div>

          <ul className="space-y-2">
            {breakdown.categories.map((category) => (
              <CategoryBar
                key={category.category_id}
                name={category.name}
                spentCents={category.spent_cents}
                refundCents={category.refund_cents}
                totalCents={total}
                largestCents={largestCategoryCents}
              />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function CategoryBar({
  name,
  spentCents,
  refundCents,
  totalCents,
  largestCents,
  muted = false,
}: {
  name: string;
  spentCents: number;
  refundCents: number;
  totalCents: number;
  largestCents: number;
  muted?: boolean;
}) {
  return (
    <li className="space-y-1">
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="truncate">{name}</span>
        <span className={`tabular-nums shrink-0 ${MUTED_CLASS}`}>
          {formatCents(spentCents)} · {formatPercent(percentOf(spentCents, totalCents))}
        </span>
      </div>
      <div className="h-2 rounded-full bg-stone-100 dark:bg-stone-800">
        <div
          className={`h-2 rounded-full ${muted ? OTHER_SERIES_CLASS : "bg-indigo-500 dark:bg-indigo-400"}`}
          style={{ width: `${percentOf(spentCents, largestCents)}%` }}
        />
      </div>
      {refundCents > 0 && (
        <div className={`text-xs ${MUTED_CLASS}`}>
          {formatCents(refundCents)} refunded
        </div>
      )}
    </li>
  );
}

// ---------------------------------------------------------------------------
// Income vs Spending
// ---------------------------------------------------------------------------

function IncomeVsSpendingSection({ insights }: { insights: Insights }) {
  const flows = insights.income_vs_spending;
  // Every scope shares one vertical scale. Independent axes would draw a €200
  // bar the same height as a €2,000 one and the side-by-side layout would
  // actively mislead.
  const axisMaxCents = Math.max(
    1,
    ...flows.flatMap((flow) =>
      flow.months.flatMap((month) => [month.income_cents, month.spent_cents]),
    ),
  );
  const showChart = insights.period.month_count > 1;

  return (
    <section className="space-y-4">
      <h2 className={SECTION_HEADING_CLASS}>Income vs Spending</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {flows.map((flow) => (
          <ScopeFlowCard
            key={flow.scope_id}
            flow={flow}
            axisMaxCents={axisMaxCents}
            showChart={showChart}
          />
        ))}
      </div>
      {showChart && (
        <p className={`text-xs ${MUTED_CLASS}`}>
          All charts share one scale, topping out at {formatCents(axisMaxCents)}.
        </p>
      )}
    </section>
  );
}

function ScopeFlowCard({
  flow,
  axisMaxCents,
  showChart,
}: {
  flow: ScopeFlow;
  axisMaxCents: number;
  showChart: boolean;
}) {
  const inTheBlack = flow.net_cents >= 0;

  return (
    <div className={CARD_CLASS}>
      <div className="px-5 py-3 border-b border-stone-200 dark:border-stone-700">
        <ScopeChip scopeId={flow.scope_id} />
      </div>
      <div className="p-5 space-y-4">
        <dl className="grid grid-cols-3 gap-3 text-sm">
          <FlowTotal label="Earned" cents={flow.income_cents} />
          <FlowTotal label="Spent" cents={flow.spent_cents} />
          <div>
            <dt className={MUTED_CLASS}>Net</dt>
            <dd
              className={`font-semibold tabular-nums ${
                inTheBlack
                  ? "text-emerald-700 dark:text-emerald-400"
                  : "text-red-700 dark:text-red-400"
              }`}
            >
              {inTheBlack ? "+" : "−"}
              {formatCents(Math.abs(flow.net_cents))}
            </dd>
          </div>
        </dl>

        {showChart && <MonthlyFlowChart flow={flow} axisMaxCents={axisMaxCents} />}

        {flow.refund_cents > 0 && (
          <p className={`text-xs ${MUTED_CLASS}`}>
            Includes {formatCents(flow.refund_cents)} refunded into categories.
          </p>
        )}
      </div>
    </div>
  );
}

function FlowTotal({ label, cents }: { label: string; cents: number }) {
  return (
    <div>
      <dt className={MUTED_CLASS}>{label}</dt>
      <dd className="font-semibold tabular-nums">{formatCents(cents)}</dd>
    </div>
  );
}

function MonthlyFlowChart({
  flow,
  axisMaxCents,
}: {
  flow: ScopeFlow;
  axisMaxCents: number;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-4 text-xs">
        <LegendSwatch className="bg-blue-600 dark:bg-blue-600" label="Earned" />
        <LegendSwatch className="bg-orange-500 dark:bg-orange-600" label="Spent" />
      </div>
      <div className="flex items-end gap-2 h-28">
        {flow.months.map((month) => (
          <div
            key={month.month}
            className="flex-1 flex flex-col items-center gap-1 h-full min-w-0"
            title={`${monthLabel(month.month)} · Earned ${formatCents(month.income_cents)} · Spent ${formatCents(month.spent_cents)}`}
          >
            <div className="flex-1 w-full flex items-end justify-center gap-0.5">
              <div
                className="flex-1 max-w-[0.875rem] rounded-t bg-blue-600 dark:bg-blue-600"
                style={{ height: `${percentOf(month.income_cents, axisMaxCents)}%` }}
              />
              <div
                className="flex-1 max-w-[0.875rem] rounded-t bg-orange-500 dark:bg-orange-600"
                style={{ height: `${percentOf(month.spent_cents, axisMaxCents)}%` }}
              />
            </div>
            <span className={`text-[10px] truncate ${MUTED_CLASS}`}>
              {shortMonthLabel(month.month)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function LegendSwatch({ className, label }: { className: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={`inline-block w-2.5 h-2.5 rounded-sm ${className}`} />
      <span className={MUTED_CLASS}>{label}</span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// Overspending
// ---------------------------------------------------------------------------

function OverspendingSection({ insights }: { insights: Insights }) {
  const {
    scopes,
    threshold_pct: thresholdPct,
    min_notable_cents: minNotableCents,
    min_baseline_months: minBaselineMonths,
  } = insights.overspending;
  const { baseline_start_month: baselineStart, baseline_end_month: baselineEnd } =
    insights.period;
  const floor = formatCents(minNotableCents);

  return (
    <section className="space-y-4">
      <h2 className={SECTION_HEADING_CLASS}>Overspending</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {scopes.map((overspending) => (
          <ScopeOverspendingCard
            key={overspending.scope_id}
            overspending={overspending}
          />
        ))}
      </div>
      <p className={`text-xs ${MUTED_CLASS}`}>
        "Usual" is a typical month between {monthLabel(baselineStart)} and{" "}
        {monthLabel(baselineEnd)}. A category is listed when it runs more than{" "}
        {Math.round(thresholdPct)}% <em>and</em> at least {floor} a month above that,
        or when its Available balance dipped {floor} or more into the red. Categories
        with less than {minBaselineMonths} months of history there are only listed for
        a negative balance.
      </p>
    </section>
  );
}

function ScopeOverspendingCard({
  overspending,
}: {
  overspending: ScopeOverspending;
}) {
  return (
    <div className={CARD_CLASS}>
      <div className="px-5 py-3 border-b border-stone-200 dark:border-stone-700 flex items-center justify-between gap-3">
        <ScopeChip scopeId={overspending.scope_id} />
        <span className={`text-sm ${MUTED_CLASS}`}>
          {overspending.on_track_count} on track
        </span>
      </div>
      {overspending.categories.length === 0 ? (
        <div className={`px-5 py-8 text-center ${MUTED_CLASS}`}>
          Nothing out of the ordinary this range.
        </div>
      ) : (
        <ul className="divide-y divide-stone-100 dark:divide-stone-800">
          {overspending.categories.map((row) => (
            <TrendRow key={row.category_id} row={row} />
          ))}
        </ul>
      )}
    </div>
  );
}

function TrendRow({ row }: { row: CategoryTrendRow }) {
  return (
    <li className="px-5 py-4 space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-medium truncate">{row.name}</div>
          <div className={`text-xs truncate ${MUTED_CLASS}`}>{row.group_name}</div>
        </div>
        {row.worst_balance_month && (
          <span className="shrink-0 px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-200 tabular-nums">
            {formatCents(row.worst_balance_cents)} in{" "}
            {monthLabel(row.worst_balance_month)}
          </span>
        )}
      </div>

      {row.has_baseline ? (
        <dl className="space-y-1 text-sm">
          <ComparisonLine
            label="Spent"
            actualCents={row.spent_cents}
            expectedCents={row.expected_spent_cents}
            deltaPct={row.spent_delta_pct}
            isNew={row.flags.includes("new_spending")}
            severity="spending"
          />
          <ComparisonLine
            label="Assigned"
            actualCents={row.assigned_cents}
            expectedCents={row.expected_assigned_cents}
            deltaPct={row.assigned_delta_pct}
            isNew={false}
            severity="neutral"
          />
        </dl>
      ) : (
        <p className={`text-sm ${MUTED_CLASS}`}>
          Spent {formatCents(row.spent_cents)}. Not enough history to compare —{" "}
          {row.baseline_month_count} of 3 months.
        </p>
      )}
    </li>
  );
}

function ComparisonLine({
  label,
  actualCents,
  expectedCents,
  deltaPct,
  isNew,
  severity,
}: {
  label: string;
  actualCents: number;
  expectedCents: number | null;
  deltaPct: number | null;
  isNew: boolean;
  severity: "spending" | "neutral";
}) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className={MUTED_CLASS}>{label}</dt>
      <dd className="flex items-baseline gap-2 tabular-nums">
        <span>{formatCents(actualCents)}</span>
        {expectedCents !== null && (
          <span className={MUTED_CLASS}>vs {formatCents(expectedCents)} usual</span>
        )}
        <DeltaPill deltaPct={deltaPct} isNew={isNew} severity={severity} />
      </dd>
    </div>
  );
}

function DeltaPill({
  deltaPct,
  isNew,
  severity,
}: {
  deltaPct: number | null;
  isNew: boolean;
  severity: "spending" | "neutral";
}) {
  const pillClass = "px-2 py-0.5 rounded-full text-xs font-medium";
  if (deltaPct === null) {
    if (!isNew) return null;
    return (
      <span
        className={`${pillClass} bg-stone-200 text-stone-700 dark:bg-stone-800 dark:text-stone-200`}
      >
        new
      </span>
    );
  }
  return (
    <span className={`${pillClass} ${deltaToneClass(deltaPct, severity)}`}>
      {formatSignedPercent(deltaPct)}
    </span>
  );
}

/**
 * Spending above the norm is a warning; assigning above it is a choice the user
 * made deliberately, so it never gets painted as a problem.
 */
function deltaToneClass(deltaPct: number, severity: "spending" | "neutral"): string {
  const neutral =
    "bg-stone-200 text-stone-700 dark:bg-stone-800 dark:text-stone-200";
  if (severity === "neutral" || deltaPct <= 0) return neutral;
  if (deltaPct > SEVERE_OVERSHOOT_PCT) {
    return "bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-200";
  }
  return "bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200";
}

function percentOf(part: number, whole: number): number {
  if (whole <= 0) return 0;
  return (part / whole) * 100;
}

function formatPercent(value: number): string {
  return `${Math.round(value)}%`;
}

function formatSignedPercent(value: number): string {
  return `${value > 0 ? "+" : ""}${Math.round(value)}%`;
}
