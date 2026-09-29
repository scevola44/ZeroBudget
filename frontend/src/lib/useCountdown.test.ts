import { describe, expect, it } from "vitest";

import { secondsRemaining } from "./useCountdown";

describe("secondsRemaining", () => {
  it("starts at the full duration", () => {
    expect(secondsRemaining(5, 0)).toBe(5);
  });

  it("rounds up so it only reaches 0 once the full wait has passed", () => {
    expect(secondsRemaining(5, 4_001)).toBe(1);
    expect(secondsRemaining(5, 4_999)).toBe(1);
    expect(secondsRemaining(5, 5_000)).toBe(0);
  });

  it("never goes negative", () => {
    expect(secondsRemaining(5, 60_000)).toBe(0);
  });
});
