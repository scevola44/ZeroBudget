import { describe, expect, it } from "vitest";

import {
  RANGE_PRESETS,
  monthsInPreset,
  monthsInRange,
  rangeLabel,
  resolveRange,
} from "./insightsRange";

describe("monthsInPreset", () => {
  it("maps the fixed presets to their month counts", () => {
    expect(monthsInPreset("1M", "2026-08")).toBe(1);
    expect(monthsInPreset("3M", "2026-08")).toBe(3);
    expect(monthsInPreset("6M", "2026-08")).toBe(6);
    expect(monthsInPreset("1Y", "2026-08")).toBe(12);
  });

  it("sizes year-to-date from the anchor's position in its year", () => {
    expect(monthsInPreset("YTD", "2026-01")).toBe(1);
    expect(monthsInPreset("YTD", "2026-08")).toBe(8);
    expect(monthsInPreset("YTD", "2025-12")).toBe(12);
  });

  it("covers every preset offered in the UI", () => {
    for (const preset of RANGE_PRESETS) {
      expect(monthsInPreset(preset, "2026-08")).toBeGreaterThan(0);
    }
  });
});

describe("resolveRange", () => {
  it("ends at the anchor for every preset", () => {
    for (const preset of RANGE_PRESETS) {
      expect(resolveRange(preset, "2026-08").endMonth).toBe("2026-08");
    }
  });

  it("counts backwards inclusively from the anchor", () => {
    expect(resolveRange("1M", "2026-08").startMonth).toBe("2026-08");
    expect(resolveRange("3M", "2026-08").startMonth).toBe("2026-06");
  });

  it("crosses a year boundary", () => {
    expect(resolveRange("1Y", "2026-08").startMonth).toBe("2025-09");
    expect(resolveRange("6M", "2026-02").startMonth).toBe("2025-09");
  });

  it("starts year-to-date in January of the anchor's year", () => {
    expect(resolveRange("YTD", "2026-08").startMonth).toBe("2026-01");
    expect(resolveRange("YTD", "2026-01").startMonth).toBe("2026-01");
  });

  it("grows year-to-date to a full year when the anchor steps back past January", () => {
    // Documented consequence of the arrow always moving one month: stepping back
    // from January lands in the previous December, whose year-to-date is twelve
    // months long.
    expect(resolveRange("YTD", "2025-12")).toEqual({
      startMonth: "2025-01",
      endMonth: "2025-12",
    });
  });
});

describe("rangeLabel", () => {
  it("names a single month in full", () => {
    expect(rangeLabel("2026-08", "2026-08")).toMatch(/August 2026/);
  });

  it("states the year once when the range stays inside it", () => {
    const label = rangeLabel("2026-06", "2026-08");
    expect(label).toMatch(/Jun/);
    expect(label).toMatch(/August 2026/);
    expect(label).not.toMatch(/2025/);
  });

  it("states both years when the range crosses one", () => {
    const label = rangeLabel("2025-09", "2026-08");
    expect(label).toMatch(/2025/);
    expect(label).toMatch(/August 2026/);
  });
});

describe("monthsInRange", () => {
  it("enumerates every month inclusively", () => {
    expect(monthsInRange("2026-06", "2026-08")).toEqual([
      "2026-06",
      "2026-07",
      "2026-08",
    ]);
  });

  it("returns the single month when both bounds match", () => {
    expect(monthsInRange("2026-08", "2026-08")).toEqual(["2026-08"]);
  });

  it("crosses a year boundary", () => {
    expect(monthsInRange("2025-11", "2026-02")).toEqual([
      "2025-11",
      "2025-12",
      "2026-01",
      "2026-02",
    ]);
  });
});
