import { describe, expect, it } from "vitest";

import { parseCsvLine } from "./csv";

describe("parseCsvLine", () => {
  it("splits plain fields and trims unquoted ones", () => {
    expect(parseCsvLine("a, b ,c")).toEqual(["a", "b", "c"]);
  });

  it("keeps commas inside quoted fields", () => {
    expect(parseCsvLine('"Groceries, Household",x')).toEqual(["Groceries, Household", "x"]);
  });

  it("unescapes doubled quotes inside quoted fields", () => {
    expect(parseCsvLine('"say ""hi""",x')).toEqual(['say "hi"', "x"]);
  });

  it("does not trim quoted fields", () => {
    expect(parseCsvLine('" padded ",x')).toEqual([" padded ", "x"]);
  });

  it("returns an empty trailing field after a trailing comma", () => {
    expect(parseCsvLine("a,b,")).toEqual(["a", "b", ""]);
  });
});

describe("parseCsvLine termination", () => {
  it("finishes on a line whose last field is quoted", () => {
    expect(parseCsvLine('"a","b"')).toEqual(["a", "b"]);
  });

  it("finishes on a single field", () => {
    expect(parseCsvLine("only")).toEqual(["only"]);
  });
});
