import { useSortable } from "@dnd-kit/sortable";

interface DragHandleProps {
  id: string | number;
}

export function DragHandle({ id }: DragHandleProps) {
  const { attributes, listeners } = useSortable({ id });

  return (
    <button
      className="text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300 cursor-grab active:cursor-grabbing transition-colors p-0 mr-2 inline-flex items-center justify-center"
      aria-label="Drag to reorder"
      {...attributes}
      {...listeners}
      type="button"
    >
      <span className="text-lg leading-none">⋮⋮</span>
    </button>
  );
}
