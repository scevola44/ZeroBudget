import { describe, expect, it } from "vitest";

import type { CategoryGroup } from "../api/types";
import {
  parseCurrencyToCents,
  parseYnabDate,
  parseYnabTransactionCsv,
  resolveCategoryId,
} from "./transactions";

const HEADER =
  "Account,Flag,Date,Payee,Category Group/Category,Category Group,Category,Memo,Outflow,Inflow,Cleared";

describe("parseCurrencyToCents", () => {
  it("parses plain and currency-prefixed amounts", () => {
    expect(parseCurrencyToCents("12.50")).toBe(1250);
    expect(parseCurrencyToCents("€12,50")).toBe(1250);
  });

  it("treats a string with both separators as European (dot = thousands)", () => {
    expect(parseCurrencyToCents("€1.234,56")).toBe(123456);
  });

  it("returns 0 for empty or unparseable input rather than failing", () => {
    expect(parseCurrencyToCents("")).toBe(0);
    expect(parseCurrencyToCents("n/a")).toBe(0);
  });
});

describe("parseYnabDate", () => {
  it("converts DD/MM/YYYY to ISO and zero-pads", () => {
    expect(parseYnabDate("28/07/2026")).toBe("2026-07-28");
    expect(parseYnabDate("1/2/2026")).toBe("2026-02-01");
  });

  it("returns input that is not three slash-separated parts unchanged", () => {
    expect(parseYnabDate("2026-07-28")).toBe("2026-07-28");
  });
});

describe("parseYnabTransactionCsv", () => {
  it("maps columns and computes the amount as inflow minus outflow", () => {
    const csv = [
      HEADER,
      "Checking,,28/07/2026,Albert Heijn,Food: Groceries,Food,Groceries,weekly shop,€42.10,€0.00,C",
    ].join("\n");

    const [spend] = parseYnabTransactionCsv(csv);

    expect(spend).toEqual({
      csvAccount: "Checking",
      date: "2026-07-28",
      payee: "Albert Heijn",
      categoryGroup: "Food",
      category: "Groceries",
      memo: "weekly shop",
      amount_cents: -4210,
    });
  });

  it("handles quoted amounts with thousands separators", () => {
    const csv = [
      HEADER,
      'Checking,,01/08/2026,Employer,,,,,"€0,00","€1.234,56",C',
    ].join("\n");

    expect(parseYnabTransactionCsv(csv)[0].amount_cents).toBe(123456);
  });

  it("skips rows without an account or a date, and blank lines", () => {
    const csv = [
      HEADER,
      ",,28/07/2026,No account,,,,,€1.00,€0.00,C",
      "Checking,,,No date,,,,,€1.00,€0.00,C",
      "",
      "Checking,,28/07/2026,Kept,,,,,€1.00,€0.00,C",
    ].join("\n");

    expect(parseYnabTransactionCsv(csv).map((row) => row.payee)).toEqual(["Kept"]);
  });

  it("truncates payee to 255 and memo to 500 characters", () => {
    const csv = [
      HEADER,
      `Checking,,28/07/2026,${"p".repeat(300)},,,,${"m".repeat(600)},€1.00,€0.00,C`,
    ].join("\n");

    const [row] = parseYnabTransactionCsv(csv);

    expect(row.payee).toHaveLength(255);
    expect(row.memo).toHaveLength(500);
  });
});

describe("resolveCategoryId", () => {
  const groups: CategoryGroup[] = [
    {
      id: 1,
      name: "Food",
      sort_order: 0,
      scope_id: 10,
      categories: [
        {
          id: 100,
          group_id: 1,
          name: "Groceries",
          sort_order: 0,
          goal_kind: "monthly",
          goal_amount_cents: 0,
          goal_target_month: null,
        },
      ],
    },
  ];

  it("finds the category by group and category name within the account's scope", () => {
    expect(resolveCategoryId("Food", "Groceries", 10, groups)).toBe(100);
  });

  it("returns null when the group belongs to another scope", () => {
    expect(resolveCategoryId("Food", "Groceries", 11, groups)).toBeNull();
  });

  it("returns null for unknown names or blank CSV cells", () => {
    expect(resolveCategoryId("Food", "Dining", 10, groups)).toBeNull();
    expect(resolveCategoryId("Fun", "Groceries", 10, groups)).toBeNull();
    expect(resolveCategoryId("", "", 10, groups)).toBeNull();
  });
});
