import { describe, expect, it } from "vitest";

import { monthLabel, shiftMonth, todayISO } from "./dates";

describe("shiftMonth", () => {
  it("moves forward within a year", () => {
    expect(shiftMonth("2026-04", 1)).toBe("2026-05");
  });

  it("moves backward within a year", () => {
    expect(shiftMonth("2026-04", -1)).toBe("2026-03");
  });

  it("wraps forward across December", () => {
    expect(shiftMonth("2026-12", 1)).toBe("2027-01");
  });

  it("wraps backward across January", () => {
    expect(shiftMonth("2026-01", -1)).toBe("2025-12");
  });

  it("handles multi-month jumps", () => {
    expect(shiftMonth("2026-04", 12)).toBe("2027-04");
    expect(shiftMonth("2026-04", -12)).toBe("2025-04");
  });

  it("pads single-digit months", () => {
    expect(shiftMonth("2026-08", 1)).toBe("2026-09");
    expect(shiftMonth("2026-09", 1)).toBe("2026-10");
  });

  it("is stable with delta=0", () => {
    expect(shiftMonth("2026-04", 0)).toBe("2026-04");
  });
});

describe("monthLabel", () => {
  it("renders a human-readable month and year", () => {
    const label = monthLabel("2026-04");
    expect(label).toMatch(/April/);
    expect(label).toMatch(/2026/);
  });
});

describe("todayISO", () => {
  it("returns a YYYY-MM-DD string", () => {
    expect(todayISO()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});
