import { describe, expect, it } from "vitest";

import { computeSplitRemaining, isSplitComplete } from "./splitRemaining";

describe("computeSplitRemaining", () => {
  it("is the full total when there are no lines yet", () => {
    expect(computeSplitRemaining(-1000, [])).toBe(-1000);
  });

  it("is zero when lines sum exactly to the total", () => {
    expect(computeSplitRemaining(-1000, [-400, -600])).toBe(0);
  });

  it("is positive when lines undershoot an outflow", () => {
    expect(computeSplitRemaining(-1000, [-400])).toBe(-600);
  });

  it("is nonzero when lines overshoot the total", () => {
    expect(computeSplitRemaining(-1000, [-400, -700])).toBe(100);
  });

  it("works for inflows too", () => {
    expect(computeSplitRemaining(1000, [600, 400])).toBe(0);
  });
});

describe("isSplitComplete", () => {
  it("is false with fewer than two lines even if balanced", () => {
    expect(isSplitComplete(-1000, [-1000])).toBe(false);
  });

  it("is false when lines don't sum to the total", () => {
    expect(isSplitComplete(-1000, [-400, -500])).toBe(false);
  });

  it("is true with two or more lines that sum exactly", () => {
    expect(isSplitComplete(-1000, [-400, -600])).toBe(true);
    expect(isSplitComplete(-1000, [-200, -300, -500])).toBe(true);
  });
});
