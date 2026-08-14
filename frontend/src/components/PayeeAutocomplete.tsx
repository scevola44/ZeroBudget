import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import type { Payee } from "../api/types";
import { useDebouncedValue } from "../lib/useDebouncedValue";

/**
 * Free-text payee input with a dropdown of past payees matching what's typed.
 *
 * Stays a real text field, not a closed picker like CategoryPicker: typing
 * text that matches nothing is always a valid submission — the backend
 * resolves it to a new payee. The dropdown is purely a shortcut for reusing
 * an existing one.
 */
export function PayeeAutocomplete({
  value,
  onChange,
  disabled,
  autoFocus,
}: {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  autoFocus?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  const debouncedValue = useDebouncedValue(value, 300);
  const suggestionsQuery = useQuery<Payee[]>({
    queryKey: ["payee-autocomplete", debouncedValue],
    queryFn: () => api<Payee[]>(`/api/payees?q=${encodeURIComponent(debouncedValue)}`),
    enabled: open && debouncedValue.trim().length > 0,
  });
  const suggestions = suggestionsQuery.data ?? [];

  useEffect(() => {
    setActiveIndex(0);
  }, [suggestions.length]);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  function pick(name: string) {
    onChange(name);
    setOpen(false);
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (!open || suggestions.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, suggestions.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && suggestions[activeIndex]) {
      e.preventDefault();
      pick(suggestions[activeIndex].name);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div className="relative" ref={containerRef}>
      <input
        autoFocus={autoFocus}
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        disabled={disabled}
        autoComplete="off"
        role="combobox"
        aria-expanded={open}
        className="w-full border border-stone-300 dark:border-stone-600 bg-transparent dark:bg-stone-900 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
      />
      {open && suggestions.length > 0 && (
        <div
          role="listbox"
          className="absolute z-20 mt-1 w-full border border-stone-200 dark:border-stone-700 bg-white dark:bg-stone-900 rounded-lg shadow-lg overflow-hidden max-h-48 overflow-y-auto"
        >
          {suggestions.map((p, index) => (
            <button
              key={p.id}
              type="button"
              role="option"
              aria-selected={index === activeIndex}
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => pick(p.name)}
              className={`w-full flex items-center px-3 py-1.5 text-sm text-left truncate ${
                index === activeIndex
                  ? "bg-indigo-50 dark:bg-indigo-900/40"
                  : "hover:bg-stone-50 dark:hover:bg-stone-800"
              }`}
            >
              {p.name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
