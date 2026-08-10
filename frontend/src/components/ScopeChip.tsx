import type { Scope } from "../api/types";
import { scopeLabel } from "../api/types";

export function ScopeChip({ scope }: { scope: Scope }) {
  const cls =
    scope === "shared"
      ? "bg-violet-100 text-violet-800 dark:bg-violet-900/50 dark:text-violet-200"
      : "bg-sky-100 text-sky-800 dark:bg-sky-900/50 dark:text-sky-200";
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}>
      {scopeLabel(scope)}
    </span>
  );
}
