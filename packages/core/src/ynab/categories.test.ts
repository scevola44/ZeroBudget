import { describe, expect, it } from "vitest";

import type { CategoryGroup } from "../api/types";
import { buildPreview, parseYnabCsv } from "./categories";

function group(name: string, categoryNames: string[]): CategoryGroup {
  return {
    id: 1,
    name,
    sort_order: 0,
    scope_id: 1,
    categories: categoryNames.map((categoryName, index) => ({
      id: index + 1,
      group_id: 1,
      name: categoryName,
      sort_order: index,
      goal_kind: "monthly",
      goal_amount_cents: 0,
      goal_target_month: null,
    })),
  };
}

describe("parseYnabCsv", () => {
  it("reads group and category from columns 2 and 3, skipping the header", () => {
    const csv = [
      "Master Category,Category Group,Category",
      ",Bills,Rent",
      ',Bills,"Gas, Electric"',
    ].join("\n");

    expect(parseYnabCsv(csv)).toEqual([
      { group: "Bills", category: "Rent" },
      { group: "Bills", category: "Gas, Electric" },
    ]);
  });

  it("skips blank lines and rows missing a group or a category", () => {
    const csv = ["header,a,b", ",Bills,", ",,Rent", "", ",Bills,Rent"].join("\r\n");

    expect(parseYnabCsv(csv)).toEqual([{ group: "Bills", category: "Rent" }]);
  });

  it("returns nothing for a file that is only a header", () => {
    expect(parseYnabCsv("header,a,b")).toEqual([]);
  });
});

describe("buildPreview", () => {
  it("marks groups and categories that do not exist yet as new", () => {
    const preview = buildPreview([{ group: "Bills", category: "Rent" }], []);

    expect(preview).toEqual([
      { name: "Bills", isNew: true, categories: [{ name: "Rent", isNew: true }] },
    ]);
  });

  it("marks an existing group as not new but still flags its missing categories", () => {
    const preview = buildPreview(
      [
        { group: "Bills", category: "Rent" },
        { group: "Bills", category: "Water" },
      ],
      [group("Bills", ["Rent"])],
    );

    expect(preview).toEqual([
      {
        name: "Bills",
        isNew: false,
        categories: [
          { name: "Rent", isNew: false },
          { name: "Water", isNew: true },
        ],
      },
    ]);
  });

  it("lists a repeated category once, in first-seen order", () => {
    const preview = buildPreview(
      [
        { group: "Fun", category: "Games" },
        { group: "Bills", category: "Rent" },
        { group: "Fun", category: "Games" },
      ],
      [],
    );

    expect(preview.map((g) => g.name)).toEqual(["Fun", "Bills"]);
    expect(preview[0].categories).toEqual([{ name: "Games", isNew: true }]);
  });
});
