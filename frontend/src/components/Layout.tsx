import { useState } from "react";
import type { ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { BrandHeader } from "./BrandHeader";

const navClass = ({ isActive }: { isActive: boolean }) =>
  `block px-4 py-2 rounded-lg text-sm font-medium ${
    isActive
      ? "bg-indigo-600 dark:bg-indigo-500 text-white"
      : "text-stone-700 dark:text-stone-300 hover:bg-stone-200 dark:hover:bg-stone-800"
  }`;

export function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);

  function closeMenu() {
    setMenuOpen(false);
  }

  return (
    <div className="min-h-screen flex bg-amber-50 dark:bg-stone-950">
      {/* Mobile backdrop */}
      {menuOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/40 md:hidden"
          onClick={closeMenu}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 w-56 bg-white dark:bg-stone-900 border-r border-stone-200 dark:border-stone-700 flex flex-col transition-transform duration-200 md:sticky md:top-0 md:h-screen md:translate-x-0 md:flex md:overflow-y-auto ${
          menuOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="px-5 py-5 border-b border-stone-200 dark:border-stone-700 flex items-center justify-between">
          <div>
            <div className="text-lg font-semibold">
              <BrandHeader />
            </div>
            <div className="text-xs text-stone-500 dark:text-stone-400">every euro has a job</div>
          </div>
          <button
            className="md:hidden p-1 rounded text-stone-500 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800"
            onClick={closeMenu}
            aria-label="Close menu"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <nav className="flex-1 overflow-y-auto p-3 space-y-1">
          <NavLink to="/budget" className={navClass} onClick={closeMenu}>
            Budget
          </NavLink>
          <NavLink to="/accounts" className={navClass} onClick={closeMenu}>
            Accounts
          </NavLink>
          <NavLink to="/categories" className={navClass} onClick={closeMenu}>
            Categories
          </NavLink>
          <NavLink to="/transactions" className={navClass} onClick={closeMenu}>
            Transactions
          </NavLink>
          <NavLink to="/insights" className={navClass} onClick={closeMenu}>
            Insights
          </NavLink>
        </nav>
        <div className="p-3 border-t border-stone-200 dark:border-stone-700 text-sm">
          <div className="text-stone-500 dark:text-stone-400 truncate mb-2">{user?.email}</div>
          <button
            onClick={() => {
              logout();
              navigate("/login", { replace: true });
            }}
            className="w-full px-3 py-1.5 rounded-lg bg-stone-100 dark:bg-stone-800 hover:bg-stone-200 dark:hover:bg-stone-700 text-stone-700 dark:text-stone-200"
          >
            Log out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Mobile top bar */}
        <header className="md:hidden flex items-center px-4 py-3 bg-white dark:bg-stone-900 border-b border-stone-200 dark:border-stone-700 sticky top-0 z-20">
          <button
            className="p-2 -ml-2 rounded text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800"
            onClick={() => setMenuOpen(true)}
            aria-label="Open menu"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <div className="ml-3 font-semibold">
            <BrandHeader />
          </div>
        </header>

        <main className="flex-1 p-4 md:p-8 overflow-x-auto">{children}</main>
      </div>
    </div>
  );
}
