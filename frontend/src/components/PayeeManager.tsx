import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { Payee } from "../api/types";

/** Collapsible rename/merge panel for the payees created by autocomplete. */
export function PayeeManager({ payees }: { payees: Payee[] }) {
  const [open, setOpen] = useState(false);
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renameError, setRenameError] = useState<string | null>(null);
  const [mergeSourceId, setMergeSourceId] = useState("");
  const [mergeTargetId, setMergeTargetId] = useState("");
  const [mergeError, setMergeError] = useState<string | null>(null);
  const qc = useQueryClient();

  function invalidate() {
    void qc.invalidateQueries({ queryKey: ["payees"] });
    void qc.invalidateQueries({ queryKey: ["transactions"] });
  }

  const rename = useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) =>
      api<Payee>(`/api/payees/${id}`, { method: "PATCH", body: { name } }),
    onSuccess: () => {
      setRenamingId(null);
      setRenameError(null);
      invalidate();
    },
    onError: (err) => setRenameError(err instanceof Error ? err.message : "Rename failed"),
  });

  const merge = useMutation({
    mutationFn: () =>
      api<{ merged_count: number }>("/api/payees/merge", {
        method: "POST",
        body: { source_id: Number(mergeSourceId), target_id: Number(mergeTargetId) },
      }),
    onSuccess: () => {
      setMergeSourceId("");
      setMergeTargetId("");
      setMergeError(null);
      invalidate();
    },
    onError: (err) => setMergeError(err instanceof Error ? err.message : "Merge failed"),
  });

  if (payees.length === 0) return null;

  return (
    <div className="bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 rounded-2xl overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-5 py-3 text-sm font-medium text-stone-700 dark:text-stone-300"
      >
        <span>Payees ({payees.length})</span>
        <span className="text-stone-400 dark:text-stone-500">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="border-t border-stone-100 dark:border-stone-800 p-5 space-y-4">
          <ul className="divide-y divide-stone-100 dark:divide-stone-800">
            {payees.map((p) => (
              <li key={p.id} className="flex items-center justify-between py-2 text-sm">
                {renamingId === p.id ? (
                  <form
                    className="flex items-center gap-2 flex-1"
                    onSubmit={(e) => {
                      e.preventDefault();
                      rename.mutate({ id: p.id, name: renameValue });
                    }}
                  >
                    <input
                      autoFocus
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      className="flex-1 border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-2 py-1"
                    />
                    <button
                      type="submit"
                      disabled={rename.isPending}
                      className="text-indigo-600 dark:text-indigo-400 hover:underline"
                    >
                      Save
                    </button>
                    <button
                      type="button"
                      onClick={() => setRenamingId(null)}
                      className="text-stone-500 dark:text-stone-400 hover:underline"
                    >
                      Cancel
                    </button>
                  </form>
                ) : (
                  <>
                    <span>{p.name}</span>
                    <button
                      onClick={() => {
                        setRenamingId(p.id);
                        setRenameValue(p.name);
                        setRenameError(null);
                      }}
                      className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline"
                    >
                      Rename
                    </button>
                  </>
                )}
              </li>
            ))}
          </ul>
          {renameError && <p className="text-sm text-red-600 dark:text-red-400">{renameError}</p>}

          {payees.length > 1 && (
            <div className="border-t border-stone-100 dark:border-stone-800 pt-4 space-y-2">
              <div className="text-sm font-medium text-stone-700 dark:text-stone-300">
                Merge duplicate payees
              </div>
              <form
                className="flex flex-wrap items-end gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (!mergeSourceId || !mergeTargetId || mergeSourceId === mergeTargetId) {
                    setMergeError("Pick two different payees.");
                    return;
                  }
                  setMergeError(null);
                  merge.mutate();
                }}
              >
                <select
                  value={mergeSourceId}
                  onChange={(e) => setMergeSourceId(e.target.value)}
                  className="h-9 border border-stone-300 dark:border-stone-600 rounded-lg px-2 text-sm bg-white dark:bg-stone-900"
                >
                  <option value="">Merge this…</option>
                  {payees.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
                <span className="text-sm text-stone-500 dark:text-stone-400">into</span>
                <select
                  value={mergeTargetId}
                  onChange={(e) => setMergeTargetId(e.target.value)}
                  className="h-9 border border-stone-300 dark:border-stone-600 rounded-lg px-2 text-sm bg-white dark:bg-stone-900"
                >
                  <option value="">…this</option>
                  {payees.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
                <button
                  type="submit"
                  disabled={merge.isPending}
                  className="border border-stone-300 dark:border-stone-600 text-stone-700 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 rounded-lg px-3 py-2 text-sm"
                >
                  Merge
                </button>
              </form>
              {mergeError && <p className="text-sm text-red-600 dark:text-red-400">{mergeError}</p>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
