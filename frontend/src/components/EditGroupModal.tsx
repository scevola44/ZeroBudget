import { useEffect, useState } from "react";
import { type CategoryGroup, type Scope, scopeLabel } from "../api/types";

export function EditGroupModal({
  group,
  isOpen,
  onClose,
  onSave,
  isPending,
  error,
}: {
  group: CategoryGroup;
  isOpen: boolean;
  onClose: () => void;
  onSave: (name: string, scope: Scope) => void;
  isPending: boolean;
  error: string | null;
}) {
  const [name, setName] = useState(group.name);
  const [scope, setScope] = useState<Scope>(group.scope);
  const hasCategories = group.categories.length > 0;
  const scopeChanged = scope !== group.scope;
  const cannotChangeScope = scopeChanged && hasCategories;

  useEffect(() => {
    if (isOpen) {
      setName(group.name);
      setScope(group.scope);
    }
  }, [isOpen, group]);

  if (!isOpen) return null;

  const nameOk = name.trim().length > 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-white dark:bg-stone-900 rounded-2xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between px-6 py-4 border-b border-stone-200 dark:border-stone-700">
          <h2 className="text-lg font-semibold">Edit category group</h2>
          <button
            type="button"
            onClick={onClose}
            disabled={isPending}
            className="text-stone-500 hover:text-stone-800 dark:hover:text-stone-200 text-xl leading-none disabled:opacity-50"
          >
            ✕
          </button>
        </div>

        <form
          className="p-6 space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (nameOk && !cannotChangeScope) {
              onSave(name.trim(), scope);
            }
          }}
        >
          <div className="space-y-1">
            <label className="text-sm font-medium text-stone-700 dark:text-stone-300">
              Group name
            </label>
            <input
              autoFocus
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={isPending}
              className="w-full border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
            />
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium text-stone-700 dark:text-stone-300">
              Scope
            </label>
            <div className="relative">
              <select
                value={scope}
                onChange={(e) => setScope(e.target.value as Scope)}
                disabled={isPending || cannotChangeScope}
                className="h-9 w-full appearance-none border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg pl-3 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
              >
                <option value="personal">{scopeLabel("personal")}</option>
                <option value="shared">{scopeLabel("shared")}</option>
              </select>
              <div className="pointer-events-none absolute inset-y-0 right-2 flex items-center text-stone-400 dark:text-stone-500">
                <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 6l4 4 4-4" />
                </svg>
              </div>
            </div>
          </div>

          {cannotChangeScope && (
            <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-900/50 rounded-lg px-3 py-2 text-sm text-yellow-800 dark:text-yellow-200">
              Cannot change scope for groups containing categories. Remove all categories first.
            </div>
          )}

          {error && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/50 rounded-lg px-3 py-2 text-sm text-red-800 dark:text-red-200">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              disabled={isPending}
              className="border border-stone-300 dark:border-stone-600 text-stone-700 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 rounded-lg px-4 py-2 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!nameOk || cannotChangeScope || isPending}
              className="bg-indigo-600 hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg px-4 py-2 text-sm font-medium"
            >
              {isPending ? "Saving…" : "Save"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
