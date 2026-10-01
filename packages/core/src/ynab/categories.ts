import type { CategoryGroup } from "../api/types";
import { parseCsvLine } from "./csv";

export type ParsedCategoryRow = { group: string; category: string };

export type PreviewGroup = {
  name: string;
  isNew: boolean;
  categories: Array<{ name: string; isNew: boolean }>;
};

export function parseYnabCsv(text: string): ParsedCategoryRow[] {
  const lines = text.split(/\r?\n/);
  const rows: ParsedCategoryRow[] = [];
  for (const line of lines.slice(1)) {
    if (!line.trim()) continue;
    const cols = parseCsvLine(line);
    const group = (cols[1] ?? "").trim();
    const category = (cols[2] ?? "").trim();
    if (group && category) rows.push({ group, category });
  }
  return rows;
}

export function buildPreview(
  parsed: ParsedCategoryRow[],
  existingGroups: CategoryGroup[]
): PreviewGroup[] {
  const existingGroupByName = new Map(existingGroups.map((g) => [g.name, g]));

  const groupMap = new Map<string, PreviewGroup>();
  for (const row of parsed) {
    if (!groupMap.has(row.group)) {
      const existing = existingGroupByName.get(row.group);
      groupMap.set(row.group, {
        name: row.group,
        isNew: !existing,
        categories: [],
      });
    }
    const previewGroup = groupMap.get(row.group)!;
    const existingGroup = existingGroupByName.get(row.group);
    const categoryExists =
      !!existingGroup &&
      existingGroup.categories.some((c) => c.name === row.category);
    if (!previewGroup.categories.some((c) => c.name === row.category)) {
      previewGroup.categories.push({ name: row.category, isNew: !categoryExists });
    }
  }

  return Array.from(groupMap.values());
}
