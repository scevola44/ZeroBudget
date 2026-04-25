import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  DndContext,
  DragEndEvent,
  closestCenter,
} from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

import { api } from "../api/client";
import type { CategoryGroup } from "../api/types";
import { DragHandle } from "../components/DragHandle";

function SortableGroupHeader({ group }: { group: CategoryGroup }) {
  const { attributes, listeners, isDragging } = useSortable({ id: `group-${group.id}` });

  return (
    <header
      {...attributes}
      {...listeners}
      className={`px-5 py-3 bg-stone-50 dark:bg-stone-800 border-b border-stone-200 dark:border-stone-700 text-sm font-semibold text-stone-700 dark:text-stone-200 flex items-center gap-2 cursor-grab active:cursor-grabbing transition-opacity ${
        isDragging ? "opacity-50" : ""
      }`}
    >
      <DragHandle id={`group-${group.id}`} />
      {group.name}
    </header>
  );
}

function SortableCategoryItem({ categoryId, categoryName, isEditing, editingCategoryName, onEditStart, onEditChange, onEditSave, onEditCancel }: any) {
  const { attributes, listeners, isDragging, transform } = useSortable({ id: `category-${categoryId}` });
  const style = {
    transform: CSS.Transform.toString(transform),
    opacity: isDragging ? 0.5 : 1,
    transition: "opacity 200ms ease",
  };

  return (
    <li
      {...attributes}
      {...listeners}
      style={style}
      className="px-5 py-2 border-t border-stone-100 dark:border-stone-800 first:border-t-0 text-sm flex items-center gap-2"
    >
      <DragHandle id={`category-${categoryId}`} />
      {isEditing ? (
        <input
          autoFocus
          value={editingCategoryName}
          onChange={onEditChange}
          onBlur={onEditSave}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              onEditSave();
            } else if (e.key === "Escape") {
              onEditCancel();
            }
          }}
          className="flex-1 border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          onClick={(e) => e.stopPropagation()}
        />
      ) : (
        <span
          onClick={() => onEditStart()}
          className="cursor-pointer hover:text-indigo-600 dark:hover:text-indigo-400 flex-1"
        >
          {categoryName}
        </span>
      )}
    </li>
  );
}

export function CategoriesPage() {
  const qc = useQueryClient();
  const groupsQuery = useQuery<CategoryGroup[]>({
    queryKey: ["category-groups"],
    queryFn: () => api<CategoryGroup[]>("/api/category-groups"),
  });

  const [newGroup, setNewGroup] = useState("");
  const [newCategoryByGroup, setNewCategoryByGroup] = useState<Record<number, string>>({});
  const [editingCategoryId, setEditingCategoryId] = useState<number | null>(null);
  const [editingCategoryName, setEditingCategoryName] = useState("");

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

  const updateCategory = useMutation({
    mutationFn: (vars: { categoryId: number; name: string }) =>
      api(`/api/categories/${vars.categoryId}`, {
        method: "PATCH",
        body: { name: vars.name },
      }),
    onSuccess: () => {
      setEditingCategoryId(null);
      void qc.invalidateQueries({ queryKey: ["category-groups"] });
      void qc.invalidateQueries({ queryKey: ["budget"] });
    },
  });

  const updateGroupOrder = useMutation({
    mutationFn: (vars: { groupId: number; sortOrder: number }) =>
      api(`/api/category-groups/${vars.groupId}`, {
        method: "PATCH",
        body: { sort_order: vars.sortOrder },
      }),
  });

  const updateCategoryOrder = useMutation({
    mutationFn: (vars: { categoryId: number; sortOrder: number }) =>
      api(`/api/categories/${vars.categoryId}`, {
        method: "PATCH",
        body: { sort_order: vars.sortOrder },
      }),
  });

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;

    if (!over || active.id === over.id) return;

    const groups = groupsQuery.data || [];
    const activeType = String(active.id).split("-")[0];
    const overType = String(over.id).split("-")[0];

    if (activeType === "group" && overType === "group") {
      const activeGroupId = parseInt(String(active.id).split("-")[1]);
      const overGroupId = parseInt(String(over.id).split("-")[1]);

      const activeIndex = groups.findIndex((g) => g.id === activeGroupId);
      const overIndex = groups.findIndex((g) => g.id === overGroupId);

      if (activeIndex === -1 || overIndex === -1) return;

      const newGroups = [...groups];
      const [movedGroup] = newGroups.splice(activeIndex, 1);
      newGroups.splice(overIndex, 0, movedGroup);

      qc.setQueryData(["category-groups"], newGroups);

      newGroups.forEach((group, index) => {
        updateGroupOrder.mutate({ groupId: group.id, sortOrder: index });
      });
    } else if (activeType === "category" && overType === "category") {
      const activeCategoryId = parseInt(String(active.id).split("-")[1]);
      const overCategoryId = parseInt(String(over.id).split("-")[1]);

      const newGroups = groups.map((group) => {
        const categories = [...group.categories];
        const activeIndex = categories.findIndex((c) => c.id === activeCategoryId);
        const overIndex = categories.findIndex((c) => c.id === overCategoryId);

        if (activeIndex === -1 || overIndex === -1) return group;

        const [movedCategory] = categories.splice(activeIndex, 1);
        categories.splice(overIndex, 0, movedCategory);

        return { ...group, categories };
      });

      qc.setQueryData(["category-groups"], newGroups);

      const groupWithCategories = newGroups.find((g) =>
        g.categories.some((c) => c.id === activeCategoryId)
      );

      if (groupWithCategories) {
        groupWithCategories.categories.forEach((category, index) => {
          updateCategoryOrder.mutate({ categoryId: category.id, sortOrder: index });
        });
      }
    }
  };

  const groupIds = (groupsQuery.data || []).map((g) => `group-${g.id}`);

  return (
    <DndContext onDragEnd={handleDragEnd} collisionDetection={closestCenter}>
      <div className="max-w-3xl space-y-6">
        <h1 className="text-2xl font-semibold">Categories</h1>

        <form
          className="bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 rounded-2xl p-5 flex flex-col sm:flex-row gap-3 sm:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            if (newGroup.trim()) createGroup.mutate(newGroup.trim());
          }}
        >
          <div className="flex-1 space-y-1">
            <label className="text-sm font-medium text-stone-700 dark:text-stone-300">New category group</label>
            <input
              value={newGroup}
              onChange={(e) => setNewGroup(e.target.value)}
              placeholder="e.g. Bills"
              className="w-full border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-2"
            />
          </div>
          <button
            type="submit"
            className="bg-indigo-600 hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600 text-white font-medium rounded-lg px-4 py-2"
          >
            Add group
          </button>
        </form>

        {groupsQuery.isLoading && <div className="text-stone-500 dark:text-stone-400">Loading…</div>}

        <SortableContext items={groupIds} strategy={verticalListSortingStrategy}>
          {groupsQuery.data?.map((group) => (
            <section
              key={group.id}
              className="bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 rounded-2xl overflow-hidden"
            >
              <SortableGroupHeader group={group} />
              <SortableContext
                items={group.categories.map((c) => `category-${c.id}`)}
                strategy={verticalListSortingStrategy}
              >
                <ul>
                  {group.categories.map((c) => (
                    <SortableCategoryItem
                      key={c.id}
                      categoryId={c.id}
                      categoryName={c.name}
                      isEditing={editingCategoryId === c.id}
                      editingCategoryName={editingCategoryName}
                      onEditStart={() => {
                        setEditingCategoryId(c.id);
                        setEditingCategoryName(c.name);
                      }}
                      onEditChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                        setEditingCategoryName(e.target.value)
                      }
                      onEditSave={() => {
                        if (editingCategoryName.trim() && editingCategoryName !== c.name) {
                          updateCategory.mutate({ categoryId: c.id, name: editingCategoryName.trim() });
                        } else {
                          setEditingCategoryId(null);
                        }
                      }}
                      onEditCancel={() => setEditingCategoryId(null)}
                    />
                  ))}
                  {group.categories.length === 0 && (
                    <li className="px-5 py-2 text-sm text-stone-500 dark:text-stone-400">No categories yet.</li>
                  )}
                </ul>
              </SortableContext>
              <form
                className="px-5 py-3 border-t border-stone-100 dark:border-stone-800 flex gap-2"
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
                  className="flex-1 border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-1.5 text-sm"
                />
                <button
                  type="submit"
                  className="bg-stone-800 hover:bg-stone-900 dark:bg-stone-700 dark:hover:bg-stone-600 text-white text-sm rounded-lg px-3 py-1.5"
                >
                  Add
                </button>
              </form>
            </section>
          ))}
        </SortableContext>

        {groupsQuery.data && groupsQuery.data.length === 0 && (
          <div className="bg-white dark:bg-stone-900 border border-dashed border-stone-300 dark:border-stone-700 rounded-2xl p-8 text-center text-stone-600 dark:text-stone-400">
            No category groups yet. Create your first one above.
          </div>
        )}
      </div>
    </DndContext>
  );
}
