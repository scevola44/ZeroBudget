import { describe, expect, it } from "vitest";

import { availabilityState } from "./budgetAvailability";

describe("availabilityState", () => {
  it("flags any negative balance as overspent, even with nothing assigned", () => {
    expect(availabilityState(0, -1)).toBe("overspent");
    expect(availabilityState(5_000, -1)).toBe("overspent");
  });

  it("treats a zero assignment with a non-negative balance as unassigned", () => {
    expect(availabilityState(0, 0)).toBe("unassigned");
    expect(availabilityState(0, 2_000)).toBe("unassigned");
  });

  it("is funded while the balance still covers what was assigned", () => {
    expect(availabilityState(5_000, 5_000)).toBe("funded");
    expect(availabilityState(5_000, 7_500)).toBe("funded");
  });

  it("is partial once some of the assignment has been spent", () => {
    expect(availabilityState(5_000, 4_999)).toBe("partial");
    expect(availabilityState(5_000, 0)).toBe("partial");
  });
});
