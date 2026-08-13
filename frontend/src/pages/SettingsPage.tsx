import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { SCOPES_QUERY_KEY, scopesApi } from "../api/scopes";
import type { Scope } from "../api/types";
import { ScopeChip } from "../components/ScopeChip";
import { useScopes } from "../lib/useScopes";

const CARD_CLASS =
  "bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 rounded-2xl";
const INPUT_CLASS =
  "w-full border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500";

export function SettingsPage() {
  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-2xl font-semibold">Settings</h1>
      <ScopesCard />
    </div>
  );
}

function ScopesCard() {
  const qc = useQueryClient();
  const { scopes, isLoading } = useScopes();
  const [newName, setNewName] = useState("");
  // One message at a time: every mutation here acts on the same short list, so
  // a second failure replacing the first is what the user expects.
  const [error, setError] = useState<string | null>(null);

  // Accounts and category groups render scope names, and the budget and
  // insights payloads are keyed by scope id, so both go stale on any change.
  const invalidateEverythingScoped = () => {
    void qc.invalidateQueries({ queryKey: SCOPES_QUERY_KEY });
    void qc.invalidateQueries({ queryKey: ["accounts"] });
    void qc.invalidateQueries({ queryKey: ["category-groups"] });
    void qc.invalidateQueries({ queryKey: ["budget"] });
    void qc.invalidateQueries({ queryKey: ["insights"] });
  };

  const failWith = (err: unknown, fallback: string) =>
    setError(err instanceof Error ? err.message : fallback);

  const createScope = useMutation({
    mutationFn: (name: string) => scopesApi.create(name),
    onSuccess: () => {
      setNewName("");
      setError(null);
      invalidateEverythingScoped();
    },
    onError: (err) => failWith(err, "Could not add that scope"),
  });

  const renameScope = useMutation({
    mutationFn: (vars: { id: number; name: string }) =>
      scopesApi.rename(vars.id, vars.name),
    onSuccess: () => {
      setError(null);
      invalidateEverythingScoped();
    },
    onError: (err) => failWith(err, "Could not rename that scope"),
  });

  const deleteScope = useMutation({
    mutationFn: (id: number) => scopesApi.remove(id),
    onSuccess: () => {
      setError(null);
      invalidateEverythingScoped();
    },
    // The server's message names what is still using the scope; repeating it
    // verbatim beats inventing a vaguer one here.
    onError: (err) => failWith(err, "Could not delete that scope"),
  });

  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-500 dark:text-stone-400">
          Scopes
        </h2>
        <p className="text-sm text-stone-600 dark:text-stone-400 mt-1">
          Each scope is an independent budget pool with its own Ready to Assign.
          Accounts and category groups belong to one. A scope still holding
          either of those can't be deleted.
        </p>
      </div>

      <div className={CARD_CLASS}>
        {isLoading ? (
          <div className="px-5 py-8 text-center text-sm text-stone-500 dark:text-stone-400">
            Loading scopes…
          </div>
        ) : (
          <ul className="divide-y divide-stone-200 dark:divide-stone-700">
            {scopes.map((scope) => (
              <ScopeRow
                key={scope.id}
                scope={scope}
                onRename={(name) => renameScope.mutate({ id: scope.id, name })}
                onDelete={() => deleteScope.mutate(scope.id)}
                isPending={renameScope.isPending || deleteScope.isPending}
                canDelete={scopes.length > 1}
              />
            ))}
          </ul>
        )}
      </div>

      {error && <div className="text-sm text-red-600 dark:text-red-400">{error}</div>}

      <form
        className="flex gap-3 items-end"
        onSubmit={(e) => {
          e.preventDefault();
          if (newName.trim()) createScope.mutate(newName.trim());
        }}
      >
        <div className="flex-1 space-y-1">
          <label className="text-sm font-medium text-stone-700 dark:text-stone-300">
            New scope
          </label>
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="e.g. Business"
            className={INPUT_CLASS}
          />
        </div>
        <button
          type="submit"
          disabled={!newName.trim() || createScope.isPending}
          className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 dark:bg-indigo-500 dark:hover:bg-indigo-600 text-white font-medium rounded-lg px-4 py-2"
        >
          Add scope
        </button>
      </form>
    </section>
  );
}

function ScopeRow({
  scope,
  onRename,
  onDelete,
  isPending,
  canDelete,
}: {
  scope: Scope;
  onRename: (name: string) => void;
  onDelete: () => void;
  isPending: boolean;
  canDelete: boolean;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const isEditing = draft !== null;

  const commit = () => {
    const name = (draft ?? "").trim();
    if (name && name !== scope.name) onRename(name);
    setDraft(null);
  };

  return (
    <li className="px-5 py-3 flex items-center gap-3">
      {isEditing ? (
        <input
          autoFocus
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit();
            if (e.key === "Escape") setDraft(null);
          }}
          disabled={isPending}
          className={`flex-1 ${INPUT_CLASS}`}
        />
      ) : (
        <>
          <ScopeChip scopeId={scope.id} />
          <span className="flex-1" />
          <button
            type="button"
            onClick={() => setDraft(scope.name)}
            disabled={isPending}
            className="text-stone-600 dark:text-stone-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors disabled:opacity-50"
            title="Rename scope"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
              />
            </svg>
          </button>
          <button
            type="button"
            onClick={onDelete}
            disabled={isPending || !canDelete}
            className="text-stone-600 dark:text-stone-400 hover:text-red-600 dark:hover:text-red-400 transition-colors disabled:opacity-30"
            title={canDelete ? "Delete scope" : "A budget needs at least one scope"}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
              />
            </svg>
          </button>
        </>
      )}
    </li>
  );
}
