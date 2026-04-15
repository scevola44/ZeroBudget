import { describe, expect, it } from "vitest";

import { formatCents, parseAmountToCents } from "./money";

describe("formatCents", () => {
  it("formats zero as €0.00", () => {
    expect(formatCents(0)).toContain("0.00");
  });

  it("formats positive values with two decimals", () => {
    const s = formatCents(12345);
    // en-IE Intl puts the symbol first; don't pin the exact whitespace.
    expect(s).toContain("123.45");
    expect(s).toContain("€");
  });

  it("formats negative values with a minus", () => {
    const s = formatCents(-5000);
    expect(s).toContain("50.00");
    expect(s).toMatch(/-/);
  });

  it("always has exactly two decimal places", () => {
    expect(formatCents(100)).toContain("1.00");
    expect(formatCents(1)).toContain("0.01");
    expect(formatCents(110)).toContain("1.10");
  });
});

describe("parseAmountToCents", () => {
  it("returns null for empty input", () => {
    expect(parseAmountToCents("")).toBeNull();
  });

  it("returns null for non-numeric input", () => {
    expect(parseAmountToCents("abc")).toBeNull();
    expect(parseAmountToCents("€€€")).toBeNull();
  });

  it("parses a plain decimal", () => {
    expect(parseAmountToCents("12.34")).toBe(1234);
  });

  it("parses an integer", () => {
    expect(parseAmountToCents("42")).toBe(4200);
  });

  it("parses a negative outflow", () => {
    expect(parseAmountToCents("-12.50")).toBe(-1250);
  });

  it("accepts a leading euro symbol", () => {
    expect(parseAmountToCents("€12.34")).toBe(1234);
  });

  it("accepts embedded whitespace", () => {
    expect(parseAmountToCents("  12.34  ")).toBe(1234);
    expect(parseAmountToCents("€ 12.34")).toBe(1234);
  });

  it("parses European comma decimals", () => {
    expect(parseAmountToCents("12,34")).toBe(1234);
    expect(parseAmountToCents("-12,50")).toBe(-1250);
  });

  it("parses European thousand separators", () => {
    // '.' is thousands, ',' is decimal → 1_234.56 EUR → 123456 cents.
    expect(parseAmountToCents("1.234,56")).toBe(123456);
    expect(parseAmountToCents("1.000.000,00")).toBe(100_000_000);
  });

  // Intentional: the parser is European-first because ','-as-thousands is
  // ambiguous with ','-as-decimal. We're EUR-only, so we commit to one.
  it("treats '1,234.56' as European (1.23456), not US 1234.56", () => {
    expect(parseAmountToCents("1,234.56")).toBe(123);
  });

  it("rounds half cents to the nearest cent", () => {
    expect(parseAmountToCents("0.005")).toBe(1);
    expect(parseAmountToCents("0.004")).toBe(0);
  });

  it("handles zero correctly", () => {
    expect(parseAmountToCents("0")).toBe(0);
    expect(parseAmountToCents("0.00")).toBe(0);
  });
});
