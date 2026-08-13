import { useEffect, useRef, useState } from "react";

import type { Account } from "../api/types";
import { availablePillClass } from "../lib/budgetAvailability";
import { partitionSuggested } from "../lib/categorySuggestions";
import { formatCents } from "../lib/money";
import { READY_TO_ASSIGN_OPTION_VALUE } from "../lib/readyToAssignOption";
import { TRANSFER_OPTION_PREFIX, transferTargetId } from "../lib/transferOption";

export type CategoryChoice = {
  id: number;
  name: string;
  groupId: number;
  groupName: string;
};

export type CategoryBudgetInfo = { assigned_cents: number; balance_cents: number };

type OptionRow = {
  type: "option";
  key: string;
  value: string;
  label: string;
  budget?: CategoryBudgetInfo;
};
type HeaderRow = { type: "header"; key: string; label: string };
type Row = OptionRow | HeaderRow;

/**
 * Grouped, searchable replacement for a native `<select>` category field.
 * Needed because per-option coloring (the remaining-budget pill) can't be
 * done with real `<option>` elements — the browser controls their styling.
 */
export function CategoryPicker({
  id,
  value,
  onChange,
  categories,
  suggestedCategoryIds = [],
  budgetByCategoryId,
  transferTargets,
  unassignedLabel = "— Unassigned (inflow) —",
  disabled,
}: {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  /** Already narrowed to the relevant account's scope by the caller. */
  categories: CategoryChoice[];
  suggestedCategoryIds?: number[];
  /** Current month's assigned/balance per category id, for the remaining-budget pill. */
  budgetByCategoryId?: Map<number, CategoryBudgetInfo>;
  /** Other accounts this transaction could become a transfer with. */
  transferTargets?: Account[];
  unassignedLabel?: string;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setActiveIndex(0);
    // Focus after the panel has actually mounted.
    const t = setTimeout(() => searchRef.current?.focus(), 0);
    return () => clearTimeout(t);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  const normalizedQuery = query.trim().toLowerCase();
  function matches(label: string): boolean {
    return normalizedQuery === "" || label.toLowerCase().includes(normalizedQuery);
  }

  const { suggested, rest } = partitionSuggested(categories, suggestedCategoryIds);

  const groups: { groupId: number; groupName: string; categories: CategoryChoice[] }[] = [];
  const groupsById = new Map<number, (typeof groups)[number]>();
  for (const c of rest) {
    let group = groupsById.get(c.groupId);
    if (!group) {
      group = { groupId: c.groupId, groupName: c.groupName, categories: [] };
      groupsById.set(c.groupId, group);
      groups.push(group);
    }
    group.categories.push(c);
  }

  function categoryOption(c: CategoryChoice): OptionRow {
    return {
      type: "option",
      key: `cat-${c.id}`,
      value: String(c.id),
      label: c.name,
      budget: budgetByCategoryId?.get(c.id),
    };
  }

  const rows: Row[] = [];

  const specialOptions: OptionRow[] = [
    { type: "option" as const, key: "unassigned", value: "", label: unassignedLabel },
    {
      type: "option" as const,
      key: "rta",
      value: READY_TO_ASSIGN_OPTION_VALUE,
      label: "Ready to Assign",
    },
  ].filter((o) => matches(o.label));
  rows.push(...specialOptions);

  const suggestedFiltered = suggested.filter((c) => matches(c.name));
  if (suggestedFiltered.length > 0) {
    rows.push({ type: "header", key: "hdr-suggested", label: "Suggested" });
    rows.push(...suggestedFiltered.map(categoryOption));
  }

  for (const group of groups) {
    const filtered = group.categories.filter((c) => matches(c.name));
    if (filtered.length === 0) continue;
    rows.push({ type: "header", key: `hdr-group-${group.groupId}`, label: group.groupName });
    rows.push(...filtered.map(categoryOption));
  }

  const filteredTransferTargets = (transferTargets ?? []).filter((a) => matches(a.name));
  if (filteredTransferTargets.length > 0) {
    rows.push({ type: "header", key: "hdr-transfer", label: "Transfer" });
    rows.push(
      ...filteredTransferTargets.map((a) => ({
        type: "option" as const,
        key: `transfer-${a.id}`,
        value: `${TRANSFER_OPTION_PREFIX}${a.id}`,
        label: `Transfer : ${a.name}`,
      })),
    );
  }

  const optionRows = rows.filter((r): r is OptionRow => r.type === "option");

  function selectRow(row: OptionRow) {
    onChange(row.value);
    setOpen(false);
  }

  function onSearchKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      setOpen(false);
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, optionRows.length - 1));
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      const active = optionRows[activeIndex];
      if (active) selectRow(active);
    }
  }

  const selectedLabel = describeSelectedValue(
    value,
    categories,
    transferTargets,
    unassignedLabel,
  );

  return (
    <div className="relative" ref={containerRef}>
      <button
        id={id}
        type="button"
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="h-9 w-full flex items-center justify-between gap-2 border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg pl-3 pr-2 text-sm text-left focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
      >
        <span className="truncate">{selectedLabel}</span>
        <svg
          className="h-4 w-4 shrink-0 text-stone-400 dark:text-stone-500"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M4 6l4 4 4-4" />
        </svg>
      </button>

      {open && (
        <div
          role="listbox"
          className="absolute z-20 mt-1 w-full border border-stone-200 dark:border-stone-700 bg-white dark:bg-stone-900 rounded-lg shadow-lg overflow-hidden"
        >
          <input
            ref={searchRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActiveIndex(0);
            }}
            onKeyDown={onSearchKeyDown}
            placeholder="Search categories"
            className="w-full border-b border-stone-200 dark:border-stone-700 bg-transparent px-3 py-2 text-sm focus:outline-none"
          />
          <div className="max-h-64 overflow-y-auto py-1">
            {rows.length === 0 && (
              <div className="px-3 py-2 text-sm text-stone-500 dark:text-stone-400">
                No matching categories.
              </div>
            )}
            {rows.map((row) => {
              if (row.type === "header") {
                return (
                  <div
                    key={row.key}
                    className="px-3 pt-2 pb-1 text-xs font-semibold uppercase tracking-wide text-stone-500 dark:text-stone-400"
                  >
                    {row.label}
                  </div>
                );
              }
              const index = optionRows.indexOf(row);
              const isActive = index === activeIndex;
              const isSelected = row.value === value;
              return (
                <button
                  key={row.key}
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  onMouseEnter={() => setActiveIndex(index)}
                  onClick={() => selectRow(row)}
                  className={`w-full flex items-center justify-between gap-3 px-3 py-1.5 text-sm text-left ${
                    isActive
                      ? "bg-indigo-50 dark:bg-indigo-900/40"
                      : "hover:bg-stone-50 dark:hover:bg-stone-800"
                  } ${isSelected ? "font-medium" : ""}`}
                >
                  <span className="truncate">{row.label}</span>
                  {row.budget && (
                    <span
                      className={`shrink-0 inline-block px-2 py-0.5 rounded-full text-xs font-semibold tabular-nums ${availablePillClass(row.budget.assigned_cents, row.budget.balance_cents)}`}
                    >
                      {formatCents(row.budget.balance_cents)}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function describeSelectedValue(
  value: string,
  categories: CategoryChoice[],
  transferTargets: Account[] | undefined,
  unassignedLabel: string,
): string {
  if (value === "") return unassignedLabel;
  if (value === READY_TO_ASSIGN_OPTION_VALUE) return "Ready to Assign";
  const transferAccountId = transferTargetId(value);
  if (transferAccountId !== null) {
    const account = transferTargets?.find((a) => a.id === transferAccountId);
    return account ? `Transfer : ${account.name}` : unassignedLabel;
  }
  const category = categories.find((c) => String(c.id) === value);
  return category ? `${category.groupName} › ${category.name}` : unassignedLabel;
}
