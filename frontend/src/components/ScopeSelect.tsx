import { Select } from "./Select";
import { useScopes } from "../lib/useScopes";

export function ScopeSelect({
  value,
  onChange,
  disabled,
}: {
  value: number | null;
  onChange: (scopeId: number) => void;
  disabled?: boolean;
}) {
  const { scopes } = useScopes();

  return (
    <Select
      value={value ?? ""}
      onChange={(selected) => onChange(Number(selected))}
      disabled={disabled}
    >
      {scopes.map((scope) => (
        <option key={scope.id} value={scope.id}>
          {scope.name}
        </option>
      ))}
    </Select>
  );
}
