// The Insights time range is always "the months ending at an anchor month".
// Presets choose how many months; the arrows move the anchor by one, whatever
// preset is active. The range itself is never stored — deriving it keeps the
// two from drifting apart.

import { monthLabel, shiftMonth } from "./dates";

export type RangePreset = "1M" | "3M" | "6M" | "YTD" | "1Y";

export const RANGE_PRESETS: readonly RangePreset[] = [
  "1M",
  "3M",
  "6M",
  "YTD",
  "1Y",
] as const;

const FIXED_PRESET_MONTHS: Record<Exclude<RangePreset, "YTD">, number> = {
  "1M": 1,
  "3M": 3,
  "6M": 6,
  "1Y": 12,
};

export type MonthRange = { startMonth: string; endMonth: string };

export function monthsInPreset(preset: RangePreset, anchorMonth: string): number {
  // Year to date runs from January, so its length depends on where the anchor
  // sits: one month in January, twelve in December.
  if (preset === "YTD") return monthNumber(anchorMonth);
  return FIXED_PRESET_MONTHS[preset];
}

export function resolveRange(preset: RangePreset, anchorMonth: string): MonthRange {
  return {
    startMonth: shiftMonth(anchorMonth, -(monthsInPreset(preset, anchorMonth) - 1)),
    endMonth: anchorMonth,
  };
}

export function rangeLabel(startMonth: string, endMonth: string): string {
  if (startMonth === endMonth) return monthLabel(endMonth);
  if (yearOf(startMonth) === yearOf(endMonth)) {
    return `${shortMonthLabel(startMonth)} – ${monthLabel(endMonth)}`;
  }
  return `${shortMonthLabel(startMonth)} ${yearOf(startMonth)} – ${monthLabel(endMonth)}`;
}

export function monthsInRange(startMonth: string, endMonth: string): string[] {
  const months: string[] = [];
  for (let month = startMonth; month <= endMonth; month = shiftMonth(month, 1)) {
    months.push(month);
  }
  return months;
}

export function shortMonthLabel(month: string): string {
  const [year, monthIndex] = month.split("-").map(Number);
  return new Date(year, monthIndex - 1, 1).toLocaleString("en-GB", { month: "short" });
}

function yearOf(month: string): string {
  return month.slice(0, 4);
}

function monthNumber(month: string): number {
  return Number(month.slice(5, 7));
}
