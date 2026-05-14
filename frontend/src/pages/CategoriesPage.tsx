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
import { scopeLabel, type Category, type CategoryGroup, type GoalKind, type YnabImportRow, type YnabImportResponse, type Scope } from "../api/types";
import { DragHandle } from "../components/DragHandle";
import { EditGroupModal } from "../components/EditGroupModal";
import { DeleteGroupConfirmModal } from "../components/DeleteGroupConfirmModal";
import { YnabImportModal } from "./YnabImportModal";
import { formatGoal } from "../lib/goal";
import { parseAmountToCents } from "../lib/money";

function ScopeChip({ scope }: { scope: Scope }) {
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

function SortableGroupHeader({
  group,
  onEditClick,
  onDeleteClick,
}: {
  group: CategoryGroup;
  onEditClick: () => void;
  onDeleteClick: () => void;
}) {
  const { attributes, listeners, isDragging } = useSortable({ id: `group-${group.id}` });

  return (
    <header
      {...attributes}
      className={`px-5 py-3 bg-stone-50 dark:bg-stone-800 border-b border-stone-200 dark:border-stone-700 text-sm font-semibold text-stone-700 dark:text-stone-200 flex items-center gap-2 transition-opacity ${
        isDragging ? "opacity-50" : ""
      }`}
    >
      <DragHandle listeners={listeners} />
      <span className="flex-1">{group.name}</span>
      <ScopeChip scope={group.scope} />
      <button
        type="button"
        onClick={onEditClick}
        className="text-stone-600 dark:text-stone-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors"
        title="Edit group"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
        </svg>
      </button>
      <button
        type="button"
        onClick={onDeleteClick}
        className="text-stone-600 dark:text-stone-400 hover:text-red-600 dark:hover:text-red-400 transition-colors"
        title="Delete group"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
        </svg>
      </button>
    </header>
  );
}

function SortableCategoryItem({
  category,
  isEditing,
  editingDraft,
  onEditStart,
  onDraftChange,
  onEditSave,
  onEditCancel,
}: {
  category: Category;
  isEditing: boolean;
  editingDraft: NewCategoryDraft;
  onEditStart: () => void;
  onDraftChange: (patch: Partial<NewCategoryDraft>) => void;
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

  const needsMonth = editingDraft.kind === "target_date";
  const amountCents = parseAmountToCents(editingDraft.amount);
  const monthOk = !needsMonth || /^\d{4}-\d{2}$/.test(editingDraft.targetMonth);
  const canSave =
    editingDraft.name.trim().length > 0 &&
    amountCents !== null &&
    amountCents > 0 &&
    monthOk;

  return (
    <li
      {...attributes}
      style={style}
      className="px-5 py-2 border-t border-stone-100 dark:border-stone-800 first:border-t-0 text-sm flex items-start gap-2"
    >
      <div className="mt-2">
        <DragHandle listeners={listeners} />
      </div>
      {isEditing ? (
        <form
          className="flex-1 grid grid-cols-1 sm:grid-cols-[1fr_auto_auto_auto] gap-2 items-center"
          onSubmit={(e) => {
            e.preventDefault();
            if (canSave) onEditSave();
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") onEditCancel();
          }}
        >
          <input
            autoFocus
            value={editingDraft.name}
            onChange={(e) => onDraftChange({ name: e.target.value })}
            placeholder="Category name"
            className="h-9 border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          <select
            value={editingDraft.kind}
            onChange={(e) => onDraftChange({ kind: e.target.value as GoalKind })}
            className="h-9 border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-2 py-1.5"
          >
            <option value="monthly">Monthly</option>
            <option value="yearly">Yearly</option>
            <option value="target_date">By a specific month</option>
          </select>
          <input
            value={editingDraft.amount}
            onChange={(e) => onDraftChange({ amount: e.target.value })}
            inputMode="decimal"
            placeholder="Amount"
            className="h-9 w-28 border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-1.5 tabular-nums"
          />
          {needsMonth && (
            <input
              type="month"
              value={editingDraft.targetMonth}
              onChange={(e) => onDraftChange({ targetMonth: e.target.value })}
              className="h-9 border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-1.5"
            />
          )}
          <div className="flex gap-1">
            <button
              type="submit"
              disabled={!canSave}
              className="h-9 bg-indigo-600 hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg px-3 py-1.5"
            >
              Save
            </button>
            <button
              type="button"
              onClick={onEditCancel}
              className="h-9 border border-stone-300 dark:border-stone-600 text-stone-700 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 rounded-lg px-3 py-1.5"
            >
              Cancel
            </button>
          </div>
        </form>
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
  const [newGroupScope, setNewGroupScope] = useState<Scope>("personal");
  const [draftByGroup, setDraftByGroup] = useState<Record<number, NewCategoryDraft>>({});
  const [editingCategoryId, setEditingCategoryId] = useState<number | null>(null);
  const [editingDraft, setEditingDraft] = useState<NewCategoryDraft>(EMPTY_DRAFT);
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [editingGroupId, setEditingGroupId] = useState<number | null>(null);
  const [deletingGroupId, setDeletingGroupId] = useState<number | null>(null);
  const [editError, setEditError] = useState<string | null>(null);

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
    mutationFn: (vars: { name: string; scope: Scope }) =>
      api("/api/category-groups", {
        method: "POST",
        body: { name: vars.name, scope: vars.scope },
      }),
    onSuccess: () => {
      setNewGroup("");
      setNewGroupScope("personal");
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
    mutationFn: (vars: {
      categoryId: number;
      name: string;
      goalKind: GoalKind;
      goalAmountCents: number;
      goalTargetMonth: string | null;
    }) =>
      api(`/api/categories/${vars.categoryId}`, {
        method: "PATCH",
        body: {
          name: vars.name,
          goal_kind: vars.goalKind,
          goal_amount_cents: vars.goalAmountCents,
          goal_target_month: vars.goalTargetMonth,
        },
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

  const updateGroup = useMutation({
    mutationFn: (vars: { groupId: number; name: string; scope: Scope }) =>
      api(`/api/category-groups/${vars.groupId}`, {
        method: "PATCH",
        body: { name: vars.name, scope: vars.scope },
      }),
    onSuccess: () => {
      setEditingGroupId(null);
      setEditError(null);
      void qc.invalidateQueries({ queryKey: ["category-groups"] });
      void qc.invalidateQueries({ queryKey: ["budget"] });
    },
    onError: (err: unknown) => {
      const message = err instanceof Error ? err.message : "Failed to update group";
      setEditError(message);
    },
  });

  const deleteGroup = useMutation({
    mutationFn: (groupId: number) =>
      api(`/api/category-groups/${groupId}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      setDeletingGroupId(null);
      void qc.invalidateQueries({ queryKey: ["category-groups"] });
      void qc.invalidateQueries({ queryKey: ["budget"] });
    },
  });

  const updateCategoryOrder = useMutation({
    mutationFn: (vars: { categoryId: number; sortOrder: number }) =>
      api(`/api/categories/${vars.categoryId}`, {
        method: "PATCH",
        body: { sort_order: vars.sortOrder },
      }),
  });

  const importYnab = useMutation({
    mutationFn: (rows: YnabImportRow[]) =>
      api<YnabImportResponse>("/api/categories/import-ynab", {
        method: "POST",
        body: { rows },
      }),
    onSuccess: () => {
      setImportModalOpen(false);
      void qc.invalidateQueries({ queryKey: ["category-groups"] });
      void qc.invalidateQueries({ queryKey: ["budget"] });
    },
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
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">Categories</h1>
          <button
            type="button"
            onClick={() => setImportModalOpen(true)}
            className="text-sm border border-stone-300 dark:border-stone-600 text-stone-700 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 rounded-lg px-3 py-1.5"
          >
            Import from YNAB
          </button>
        </div>

        <form
          className="bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 rounded-2xl p-5 flex flex-col sm:flex-row gap-3 sm:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            if (newGroup.trim()) createGroup.mutate({ name: newGroup.trim(), scope: newGroupScope });
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
          <div className="space-y-1">
            <label className="text-sm font-medium text-stone-700 dark:text-stone-300">Scope</label>
            <select
              value={newGroupScope}
              onChange={(e) => setNewGroupScope(e.target.value as Scope)}
              className="border border-stone-300 dark:border-stone-600 rounded-lg px-3 py-2 bg-white dark:bg-stone-900"
            >
              <option value="personal">Personal</option>
              <option value="shared">Family</option>
            </select>
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
              <SortableGroupHeader
                group={group}
                onEditClick={() => {
                  setEditingGroupId(group.id);
                  setEditError(null);
                }}
                onDeleteClick={() => setDeletingGroupId(group.id)}
              />
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
                      editingDraft={editingDraft}
                      onEditStart={() => {
                        setEditingCategoryId(c.id);
                        setEditingDraft({
                          name: c.name,
                          kind: c.goal_kind,
                          amount: (c.goal_amount_cents / 100).toFixed(2),
                          targetMonth: c.goal_target_month?.slice(0, 7) ?? "",
                        });
                      }}
                      onDraftChange={(patch) => setEditingDraft((d) => ({ ...d, ...patch }))}
                      onEditSave={() => {
                        const trimmedName = editingDraft.name.trim();
                        const amountCents = parseAmountToCents(editingDraft.amount);
                        const needsMonth = editingDraft.kind === "target_date";
                        if (
                          !trimmedName ||
                          !amountCents ||
                          amountCents <= 0 ||
                          (needsMonth && !/^\d{4}-\d{2}$/.test(editingDraft.targetMonth))
                        ) return;
                        updateCategory.mutate({
                          categoryId: c.id,
                          name: trimmedName,
                          goalKind: editingDraft.kind,
                          goalAmountCents: amountCents,
                          goalTargetMonth: needsMonth ? `${editingDraft.targetMonth}-01` : null,
                        });
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

      {importModalOpen && (
        <YnabImportModal
          existingGroups={groupsQuery.data ?? []}
          onImport={(rows) => importYnab.mutate(rows)}
          isPending={importYnab.isPending}
          onClose={() => setImportModalOpen(false)}
        />
      )}

      {editingGroupId !== null && groupsQuery.data && (
        <EditGroupModal
          group={groupsQuery.data.find((g) => g.id === editingGroupId)!}
          isOpen={true}
          onClose={() => {
            setEditingGroupId(null);
            setEditError(null);
          }}
          onSave={(name, scope) => {
            updateGroup.mutate({ groupId: editingGroupId, name, scope });
          }}
          isPending={updateGroup.isPending}
          error={editError}
        />
      )}

      {deletingGroupId !== null && groupsQuery.data && (
        <DeleteGroupConfirmModal
          group={groupsQuery.data.find((g) => g.id === deletingGroupId)!}
          isOpen={true}
          onClose={() => setDeletingGroupId(null)}
          onConfirm={() => deleteGroup.mutate(deletingGroupId)}
          isPending={deleteGroup.isPending}
        />
      )}
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
        className="h-9 border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-1.5 text-sm"
      />
      <select
        value={draft.kind}
        onChange={(e) => onChange({ kind: e.target.value as GoalKind })}
        className="h-9 border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-2 py-1.5 text-sm"
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
        className="h-9 w-28 border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-1.5 text-sm tabular-nums"
      />
      {needsMonth && (
        <input
          type="month"
          value={draft.targetMonth}
          onChange={(e) => onChange({ targetMonth: e.target.value })}
          className="h-9 border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-1.5 text-sm"
        />
      )}
      <button
        type="submit"
        disabled={!canSubmit}
        className="h-9 bg-stone-800 hover:bg-stone-900 dark:bg-stone-700 dark:hover:bg-stone-600 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm rounded-lg px-3 py-1.5"
      >
        Add
      </button>
    </form>
  );
}
