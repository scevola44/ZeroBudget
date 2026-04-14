import type { ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

const navClass = ({ isActive }: { isActive: boolean }) =>
  `block px-4 py-2 rounded-lg text-sm font-medium ${
    isActive ? "bg-indigo-600 text-white" : "text-slate-700 hover:bg-slate-200"
  }`;

export function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex">
      <aside className="w-56 bg-white border-r border-slate-200 flex flex-col">
        <div className="px-5 py-5 border-b border-slate-200">
          <div className="text-lg font-semibold">ZeroBudget</div>
          <div className="text-xs text-slate-500">every euro has a job</div>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          <NavLink to="/budget" className={navClass}>
            Budget
          </NavLink>
          <NavLink to="/accounts" className={navClass}>
            Accounts
          </NavLink>
          <NavLink to="/categories" className={navClass}>
            Categories
          </NavLink>
        </nav>
        <div className="p-3 border-t border-slate-200 text-sm">
          <div className="text-slate-500 truncate mb-2">{user?.email}</div>
          <button
            onClick={() => {
              logout();
              navigate("/login", { replace: true });
            }}
            className="w-full px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700"
          >
            Log out
          </button>
        </div>
      </aside>
      <main className="flex-1 p-8 overflow-x-auto">{children}</main>
    </div>
  );
}
