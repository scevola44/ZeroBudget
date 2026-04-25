import type { DraggableSyntheticListeners } from "@dnd-kit/core";

interface DragHandleProps {
  listeners: DraggableSyntheticListeners;
}

export function DragHandle({ listeners }: DragHandleProps) {
  return (
    <button
      className="text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300 cursor-grab active:cursor-grabbing transition-colors p-0 mr-2 inline-flex items-center justify-center"
      aria-label="Drag to reorder"
      {...listeners}
      type="button"
    >
      <span className="text-lg leading-none">⋮⋮</span>
    </button>
  );
}
