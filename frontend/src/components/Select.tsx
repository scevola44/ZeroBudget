import { ReactNode } from "react";

export function Select({
  value,
  onChange,
  disabled,
  className,
  children,
  autoFocus,
  defaultValue,
  onBlur,
  onKeyDown,
}: {
  value?: string | number;
  onChange: (value: string) => void;
  disabled?: boolean;
  className?: string;
  children: ReactNode;
  autoFocus?: boolean;
  defaultValue?: string | number;
  onBlur?: () => void;
  onKeyDown?: (e: React.KeyboardEvent) => void;
}) {
  const baseClasses = "h-9 w-full appearance-none border rounded-lg pl-3 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50";
  const borderClasses = "border-stone-300 dark:border-stone-600";
  const bgClasses = "bg-white dark:bg-stone-900";

  const finalClassName = className
    ? `${baseClasses} ${className}`
    : `${baseClasses} ${borderClasses} ${bgClasses}`;

  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className={finalClassName}
        autoFocus={autoFocus}
        defaultValue={defaultValue}
        onBlur={onBlur}
        onKeyDown={onKeyDown}
      >
        {children}
      </select>
      <div className="pointer-events-none absolute inset-y-0 right-2 flex items-center text-stone-400 dark:text-stone-500">
        <svg
          className="h-4 w-4"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M4 6l4 4 4-4" />
        </svg>
      </div>
    </div>
  );
}
