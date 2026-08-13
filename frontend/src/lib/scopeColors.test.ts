import { describe, expect, it } from "vitest";

import {
  SCOPE_PALETTE_SIZE,
  scopeBarClass,
  scopeChipClass,
} from "./scopeColors";

describe("scopeChipClass", () => {
  it("keeps the sky and violet the seeded scopes have always rendered in", () => {
    expect(scopeChipClass(0)).toContain("sky");
    expect(scopeChipClass(1)).toContain("violet");
  });

  it("gives every palette slot a distinct colour", () => {
    const classes = Array.from({ length: SCOPE_PALETTE_SIZE }, (_, i) => scopeChipClass(i));
    expect(new Set(classes).size).toBe(SCOPE_PALETTE_SIZE);
  });

  it("wraps rather than running off the end of the palette", () => {
    expect(scopeChipClass(SCOPE_PALETTE_SIZE)).toBe(scopeChipClass(0));
    expect(scopeChipClass(SCOPE_PALETTE_SIZE + 1)).toBe(scopeChipClass(1));
  });

  it("never interpolates, so every class is a literal Tailwind name", () => {
    // A class built by interpolation would produce no CSS; the giveaway is a
    // template-literal artefact surviving into the output.
    expect(scopeChipClass(0)).not.toContain("${");
  });
});

describe("scopeBarClass", () => {
  it("matches the chip palette slot for slot", () => {
    expect(scopeBarClass(0)).toContain("sky");
    expect(scopeBarClass(1)).toContain("violet");
  });

  it("wraps like the chip palette", () => {
    expect(scopeBarClass(SCOPE_PALETTE_SIZE)).toBe(scopeBarClass(0));
  });
});
