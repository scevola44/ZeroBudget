import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { CategoryGroup } from "../api/types";

export function CategoriesPage() {
  const qc = useQueryClient();
  const groupsQuery = useQuery<CategoryGroup[]>({
    queryKey: ["category-groups"],
    queryFn: () => api<CategoryGroup[]>("/api/category-groups"),
  });

  const [newGroup, setNewGroup] = useState("");
  const [newCategoryByGroup, setNewCategoryByGroup] = useState<Record<number, string>>({});

  const createGroup = useMutation({
    mutationFn: (name: string) =>
      api("/api/category-groups", { method: "POST", body: { name } }),
    onSuccess: () => {
      setNewGroup("");
      void qc.invalidateQueries({ queryKey: ["category-groups"] });
      void qc.invalidateQueries({ queryKey: ["budget"] });
    },
  });

  const createCategory = useMutation({
    mutationFn: (vars: { groupId: number; name: string }) =>
      api("/api/categories", {
        method: "POST",
        body: { group_id: vars.groupId, name: vars.name },
      }),
    onSuccess: (_data, vars) => {
      setNewCategoryByGroup((m) => ({ ...m, [vars.groupId]: "" }));
      void qc.invalidateQueries({ queryKey: ["category-groups"] });
      void qc.invalidateQueries({ queryKey: ["budget"] });
    },
  });

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold">Categories</h1>

      <form
        className="bg-white border border-slate-200 rounded-2xl p-5 flex flex-col sm:flex-row gap-3 sm:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          if (newGroup.trim()) createGroup.mutate(newGroup.trim());
        }}
      >
        <div className="flex-1 space-y-1">
          <label className="text-sm font-medium text-slate-700">New category group</label>
          <input
            value={newGroup}
            onChange={(e) => setNewGroup(e.target.value)}
            placeholder="e.g. Bills"
            className="w-full border border-slate-300 rounded-lg px-3 py-2"
          />
        </div>
        <button
          type="submit"
          className="bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded-lg px-4 py-2"
        >
          Add group
        </button>
      </form>

      {groupsQuery.isLoading && <div className="text-slate-500">Loading…</div>}

      {groupsQuery.data?.map((group) => (
        <section
          key={group.id}
          className="bg-white border border-slate-200 rounded-2xl overflow-hidden"
        >
          <header className="px-5 py-3 bg-slate-50 border-b border-slate-200 text-sm font-semibold text-slate-700">
            {group.name}
          </header>
          <ul>
            {group.categories.map((c) => (
              <li
                key={c.id}
                className="px-5 py-2 border-t border-slate-100 first:border-t-0 text-sm"
              >
                {c.name}
              </li>
            ))}
            {group.categories.length === 0 && (
              <li className="px-5 py-2 text-sm text-slate-500">No categories yet.</li>
            )}
          </ul>
          <form
            className="px-5 py-3 border-t border-slate-100 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              const name = (newCategoryByGroup[group.id] ?? "").trim();
              if (name) createCategory.mutate({ groupId: group.id, name });
            }}
          >
            <input
              value={newCategoryByGroup[group.id] ?? ""}
              onChange={(e) =>
                setNewCategoryByGroup((m) => ({ ...m, [group.id]: e.target.value }))
              }
              placeholder="New category"
              className="flex-1 border border-slate-300 rounded-lg px-3 py-1.5 text-sm"
            />
            <button
              type="submit"
              className="bg-slate-800 hover:bg-slate-900 text-white text-sm rounded-lg px-3 py-1.5"
            >
              Add
            </button>
          </form>
        </section>
      ))}

      {groupsQuery.data && groupsQuery.data.length === 0 && (
        <div className="bg-white border border-dashed border-slate-300 rounded-2xl p-8 text-center text-slate-600">
          No category groups yet. Create your first one above.
        </div>
      )}
    </div>
  );
}
