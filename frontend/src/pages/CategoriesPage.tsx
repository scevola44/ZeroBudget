import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  DndContext,
  DragEndEvent,
  closestCenter,
  MouseSensor,
  TouchSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

import { api } from "../api/client";
import type { Category, CategoryGroup, GoalKind } from "../api/types";
import { DragHandle } from "../components/DragHandle";
import { formatGoal } from "../lib/goal";
import { parseAmountToCents } from "../lib/money";

function SortableGroupHeader({ group }: { group: CategoryGroup }) {
  const { attributes, listeners, isDragging } = useSortable({ id: `group-${group.id}` });

  return (
    <header
      {...attributes}
      className={`px-5 py-3 bg-stone-50 dark:bg-stone-800 border-b border-stone-200 dark:border-stone-700 text-sm font-semibold text-stone-700 dark:text-stone-200 flex items-center gap-2 transition-opacity ${
        isDragging ? "opacity-50" : ""
      }`}
    >
      <DragHandle listeners={listeners} />
      {group.name}
    </header>
  );
}

function SortableCategoryItem({
  category,
  isEditing,
  editingCategoryName,
  onEditStart,
  onEditChange,
  onEditSave,
  onEditCancel,
}: {
  category: Category;
  isEditing: boolean;
  editingCategoryName: string;
  onEditStart: () => void;
  onEditChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onEditSave: () => void;
  onEditCancel: () => void;
}) {
  const { attributes, listeners, isDragging, transform } = useSortable({
    id: `category-${category.id}`,
  });
  const style = {
    transform: CSS.Transform.toString(transform),
    opacity: isDragging ? 0.5 : 1,
    transition: "opacity 200ms ease",
  };

  return (
    <li
      {...attributes}
      style={style}
      className="px-5 py-2 border-t border-stone-100 dark:border-stone-800 first:border-t-0 text-sm flex items-center gap-2"
    >
      <DragHandle listeners={listeners} />
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
        <button
          type="button"
          onClick={() => onEditStart()}
          className="text-left cursor-pointer flex-1 group"
        >
          <div className="group-hover:text-indigo-600 dark:group-hover:text-indigo-400">
            {category.name}
          </div>
          <div className="text-xs text-stone-500 dark:text-stone-400">
            {formatGoal(category)}
          </div>
        </button>
      )}
    </li>
  );
}

type NewCategoryDraft = {
  name: string;
  kind: GoalKind;
  amount: string;
  targetMonth: string;
};

const EMPTY_DRAFT: NewCategoryDraft = {
  name: "",
  kind: "monthly",
  amount: "",
  targetMonth: "",
};

export function CategoriesPage() {
  const qc = useQueryClient();
  const sensors = useSensors(
    useSensor(MouseSensor),
    useSensor(TouchSensor, {
      activationConstraint: { delay: 250, tolerance: 5 },
    })
  );
  const groupsQuery = useQuery<CategoryGroup[]>({
    queryKey: ["category-groups"],
    queryFn: () => api<CategoryGroup[]>("/api/category-groups"),
  });

  const [newGroup, setNewGroup] = useState("");
  const [draftByGroup, setDraftByGroup] = useState<Record<number, NewCategoryDraft>>({});
  const [editingCategoryId, setEditingCategoryId] = useState<number | null>(null);
  const [editingCategoryName, setEditingCategoryName] = useState("");

  function getDraft(groupId: number): NewCategoryDraft {
    return draftByGroup[groupId] ?? EMPTY_DRAFT;
  }
  function setDraft(groupId: number, patch: Partial<NewCategoryDraft>) {
    setDraftByGroup((m) => ({ ...m, [groupId]: { ...getDraft(groupId), ...patch } }));
  }
  function resetDraft(groupId: number) {
    setDraftByGroup((m) => ({ ...m, [groupId]: EMPTY_DRAFT }));
  }

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
    mutationFn: (vars: {
      groupId: number;
      name: string;
      goalKind: GoalKind;
      goalAmountCents: number;
      goalTargetMonth: string | null;
    }) =>
      api("/api/categories", {
        method: "POST",
        body: {
          group_id: vars.groupId,
          name: vars.name,
          goal_kind: vars.goalKind,
          goal_amount_cents: vars.goalAmountCents,
          ...(vars.goalTargetMonth !== null
            ? { goal_target_month: vars.goalTargetMonth }
            : {}),
        },
      }),
    onSuccess: (_data, vars) => {
      resetDraft(vars.groupId);
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
    <DndContext sensors={sensors} onDragEnd={handleDragEnd} collisionDetection={closestCenter}>
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
                      category={c}
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
              <NewCategoryForm
                groupId={group.id}
                draft={getDraft(group.id)}
                onChange={(patch) => setDraft(group.id, patch)}
                onSubmit={(payload) => createCategory.mutate(payload)}
              />
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

function NewCategoryForm({
  groupId,
  draft,
  onChange,
  onSubmit,
}: {
  groupId: number;
  draft: NewCategoryDraft;
  onChange: (patch: Partial<NewCategoryDraft>) => void;
  onSubmit: (vars: {
    groupId: number;
    name: string;
    goalKind: GoalKind;
    goalAmountCents: number;
    goalTargetMonth: string | null;
  }) => void;
}) {
  const name = draft.name.trim();
  const amountCents = parseAmountToCents(draft.amount);
  const needsMonth = draft.kind === "target_date";
  const monthOk = !needsMonth || /^\d{4}-\d{2}$/.test(draft.targetMonth);
  const canSubmit = name.length > 0 && amountCents !== null && amountCents > 0 && monthOk;

  return (
    <form
      className="px-5 py-3 border-t border-stone-100 dark:border-stone-800 grid grid-cols-1 sm:grid-cols-[1fr_auto_auto_auto] gap-2 sm:items-end"
      onSubmit={(e) => {
        e.preventDefault();
        if (!canSubmit) return;
        onSubmit({
          groupId,
          name,
          goalKind: draft.kind,
          goalAmountCents: amountCents!,
          goalTargetMonth: needsMonth ? `${draft.targetMonth}-01` : null,
        });
      }}
    >
      <input
        value={draft.name}
        onChange={(e) => onChange({ name: e.target.value })}
        placeholder="New category"
        className="border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-1.5 text-sm"
      />
      <select
        value={draft.kind}
        onChange={(e) => onChange({ kind: e.target.value as GoalKind })}
        className="border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-2 py-1.5 text-sm"
      >
        <option value="monthly">Monthly</option>
        <option value="yearly">Yearly</option>
        <option value="target_date">By a specific month</option>
      </select>
      <input
        value={draft.amount}
        onChange={(e) => onChange({ amount: e.target.value })}
        inputMode="decimal"
        placeholder="Amount"
        className="w-28 border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-1.5 text-sm tabular-nums"
      />
      {needsMonth && (
        <input
          type="month"
          value={draft.targetMonth}
          onChange={(e) => onChange({ targetMonth: e.target.value })}
          className="border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-1.5 text-sm"
        />
      )}
      <button
        type="submit"
        disabled={!canSubmit}
        className="bg-stone-800 hover:bg-stone-900 dark:bg-stone-700 dark:hover:bg-stone-600 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm rounded-lg px-3 py-1.5"
      >
        Add
      </button>
    </form>
  );
}
