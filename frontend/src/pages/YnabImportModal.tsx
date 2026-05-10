import { useRef, useState } from "react";
import type { CategoryGroup } from "../api/types";
import type { YnabImportRow } from "../api/types";

type ParsedRow = { group: string; category: string };

type PreviewGroup = {
  name: string;
  isNew: boolean;
  categories: Array<{ name: string; isNew: boolean }>;
};

function parseCsvLine(line: string): string[] {
  const fields: string[] = [];
  let i = 0;
  while (i <= line.length) {
    if (line[i] === '"') {
      i++;
      let field = "";
      while (i < line.length) {
        if (line[i] === '"' && line[i + 1] === '"') {
          field += '"';
          i += 2;
        } else if (line[i] === '"') {
          i++;
          break;
        } else {
          field += line[i++];
        }
      }
      fields.push(field);
      if (line[i] === ",") i++;
    } else {
      let field = "";
      while (i < line.length && line[i] !== ",") field += line[i++];
      fields.push(field.trim());
      if (line[i] === ",") i++;
    }
  }
  return fields;
}

function parseYnabCsv(text: string): ParsedRow[] {
  const lines = text.split(/\r?\n/);
  const rows: ParsedRow[] = [];
  for (const line of lines.slice(1)) {
    if (!line.trim()) continue;
    const cols = parseCsvLine(line);
    const group = (cols[1] ?? "").trim();
    const category = (cols[2] ?? "").trim();
    if (group && category) rows.push({ group, category });
  }
  return rows;
}

function buildPreview(
  parsed: ParsedRow[],
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

export function YnabImportModal({
  existingGroups,
  onImport,
  isPending,
  onClose,
}: {
  existingGroups: CategoryGroup[];
  onImport: (rows: YnabImportRow[]) => void;
  isPending: boolean;
  onClose: () => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<PreviewGroup[] | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);

  function handleFile(file: File) {
    setFileError(null);
    setPreview(null);
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      const parsed = parseYnabCsv(text);
      if (parsed.length === 0) {
        setFileError("No valid rows found. Make sure this is a YNAB categories CSV.");
        return;
      }
      setPreview(buildPreview(parsed, existingGroups));
    };
    reader.readAsText(file);
  }

  const newGroupsCount = preview?.filter((g) => g.isNew).length ?? 0;
  const newCatsCount =
    preview?.flatMap((g) => g.categories).filter((c) => c.isNew).length ?? 0;
  const canImport = newGroupsCount > 0 || newCatsCount > 0;

  function handleImport() {
    if (!preview) return;
    const rows: YnabImportRow[] = [];
    for (const group of preview) {
      for (const cat of group.categories) {
        if (cat.isNew) rows.push({ group: group.name, category: cat.name });
      }
    }
    onImport(rows);
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-white dark:bg-stone-900 rounded-2xl shadow-xl w-full max-w-2xl max-h-[85vh] flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-stone-200 dark:border-stone-700">
          <h2 className="text-lg font-semibold">Import from YNAB</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-stone-500 hover:text-stone-800 dark:hover:text-stone-200 text-xl leading-none"
          >
            ✕
          </button>
        </div>

        <div className="p-6 overflow-y-auto flex-1 space-y-5">
          <p className="text-sm text-stone-600 dark:text-stone-400">
            Export your categories from YNAB via <em>Budget → All Categories → Export</em>, then
            upload the CSV here. Goals can be set after import.
          </p>

          <div>
            <input
              ref={fileRef}
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFile(file);
              }}
            />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="border border-dashed border-stone-400 dark:border-stone-600 rounded-xl px-4 py-3 text-sm text-stone-600 dark:text-stone-400 hover:border-indigo-500 hover:text-indigo-600 dark:hover:text-indigo-400 w-full text-center transition-colors"
            >
              {preview ? "Choose a different file" : "Choose CSV file…"}
            </button>
            {fileError && (
              <p className="mt-2 text-sm text-red-600 dark:text-red-400">{fileError}</p>
            )}
          </div>

          {preview && (
            <div className="space-y-3">
              <p className="text-sm font-medium text-stone-700 dark:text-stone-300">
                Preview
                <span className="ml-2 font-normal text-stone-500 dark:text-stone-400">
                  {newGroupsCount > 0 && `${newGroupsCount} new group${newGroupsCount !== 1 ? "s" : ""}`}
                  {newGroupsCount > 0 && newCatsCount > 0 && ", "}
                  {newCatsCount > 0 && `${newCatsCount} new categor${newCatsCount !== 1 ? "ies" : "y"}`}
                  {!canImport && "nothing new to import"}
                </span>
              </p>

              <div className="border border-stone-200 dark:border-stone-700 rounded-xl overflow-hidden divide-y divide-stone-100 dark:divide-stone-800">
                {preview.map((group) => (
                  <div key={group.name}>
                    <div className="px-4 py-2 bg-stone-50 dark:bg-stone-800 flex items-center justify-between">
                      <span className="text-sm font-semibold text-stone-700 dark:text-stone-200 truncate">
                        {group.name}
                      </span>
                      <Badge isNew={group.isNew} />
                    </div>
                    <ul className="divide-y divide-stone-50 dark:divide-stone-800/60">
                      {group.categories.map((cat) => (
                        <li
                          key={cat.name}
                          className="px-4 py-1.5 flex items-center justify-between text-sm"
                        >
                          <span className="text-stone-700 dark:text-stone-300 truncate">
                            {cat.name}
                          </span>
                          <Badge isNew={cat.isNew} />
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3 px-6 py-4 border-t border-stone-200 dark:border-stone-700">
          <button
            type="button"
            onClick={onClose}
            disabled={isPending}
            className="border border-stone-300 dark:border-stone-600 text-stone-700 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 rounded-lg px-4 py-2 text-sm disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleImport}
            disabled={!preview || !canImport || isPending}
            className="bg-indigo-600 hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg px-4 py-2 text-sm font-medium"
          >
            {isPending
              ? "Importing…"
              : canImport
              ? `Import ${newGroupsCount + newCatsCount} item${newGroupsCount + newCatsCount !== 1 ? "s" : ""}`
              : "Nothing to import"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Badge({ isNew }: { isNew: boolean }) {
  return isNew ? (
    <span className="ml-3 shrink-0 text-xs font-medium bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300 rounded-full px-2 py-0.5">
      New
    </span>
  ) : (
    <span className="ml-3 shrink-0 text-xs text-stone-400 dark:text-stone-500">
      Exists
    </span>
  );
}
