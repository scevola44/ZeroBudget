import { describe, expect, it } from "vitest";

import {
  CHART_SERIES_CLASSES,
  MAX_SERIES,
  OTHER_SERIES_CLASS,
  seriesClass,
} from "./chartColors";

describe("seriesClass", () => {
  it("gives each slot its own colour", () => {
    const classes = CHART_SERIES_CLASSES.map((_, index) => seriesClass(index));
    expect(new Set(classes).size).toBe(MAX_SERIES);
  });

  it("folds anything past the last slot into one neutral colour", () => {
    expect(seriesClass(MAX_SERIES)).toBe(OTHER_SERIES_CLASS);
    expect(seriesClass(MAX_SERIES + 5)).toBe(OTHER_SERIES_CLASS);
  });

  it("never cycles back to a colour already in use", () => {
    expect(CHART_SERIES_CLASSES).not.toContain(seriesClass(MAX_SERIES));
  });
});

describe("the palette itself", () => {
  it("ships a dark variant for every entry, so nothing vanishes in dark mode", () => {
    for (const entry of [...CHART_SERIES_CLASSES, OTHER_SERIES_CLASS]) {
      expect(entry).toMatch(/^bg-[a-z]+-\d+ dark:bg-[a-z]+-\d+$/);
    }
  });

  it("keeps every class literal, since Tailwind cannot see interpolated names", () => {
    for (const entry of [...CHART_SERIES_CLASSES, OTHER_SERIES_CLASS]) {
      expect(entry).not.toContain("${");
    }
  });
});
