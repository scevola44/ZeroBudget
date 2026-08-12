import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { BrandHeader } from "../components/BrandHeader";

export function LegalLayout({
  title,
  updated,
  children,
}: {
  title: string;
  updated: string;
  children: ReactNode;
}) {
  return (
    <div className="min-h-screen px-4 py-10 flex flex-col items-center">
      <div className="w-full max-w-3xl space-y-6">
        <BrandHeader />
        <div className="bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 rounded-2xl shadow-sm p-6 sm:p-8 space-y-6">
          <div className="space-y-1">
            <h1 className="text-2xl font-semibold">{title}</h1>
            <p className="text-sm text-stone-500 dark:text-stone-400">Last updated {updated}</p>
          </div>
          <div className="space-y-6 text-sm text-stone-700 dark:text-stone-300 leading-relaxed">
            {children}
          </div>
        </div>
        <Link to="/login" className="text-sm text-indigo-600 dark:text-indigo-400 hover:underline">
          ← Back to login
        </Link>
      </div>
    </div>
  );
}

export function LegalSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="text-base font-semibold text-stone-900 dark:text-stone-100">{title}</h2>
      <div className="space-y-2">{children}</div>
    </section>
  );
}
