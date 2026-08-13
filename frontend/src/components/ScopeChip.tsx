import { useScopes } from "../lib/useScopes";
import { scopeChipClass } from "../lib/scopeColors";

export function ScopeChip({ scopeId }: { scopeId: number }) {
  const { scopeById } = useScopes();
  const scope = scopeById.get(scopeId);
  if (!scope) return null;

  return (
    <span
      className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${scopeChipClass(
        scope.sort_order,
      )}`}
    >
      {scope.name}
    </span>
  );
}
