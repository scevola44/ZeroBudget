import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { Account } from "../api/types";
import { formatCents } from "../lib/money";

export function AccountsPage() {
  const qc = useQueryClient();
  const accountsQuery = useQuery<Account[]>({
    queryKey: ["accounts"],
    queryFn: () => api<Account[]>("/api/accounts"),
  });

  const [name, setName] = useState("");
  const [type, setType] = useState("checking");

  const createMutation = useMutation({
    mutationFn: (body: { name: string; type: string }) =>
      api<Account>("/api/accounts", { method: "POST", body }),
    onSuccess: () => {
      setName("");
      void qc.invalidateQueries({ queryKey: ["accounts"] });
    },
  });

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold">Accounts</h1>

      <form
        className="bg-white border border-slate-200 rounded-2xl p-5 flex flex-col sm:flex-row gap-3 sm:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim()) createMutation.mutate({ name: name.trim(), type });
        }}
      >
        <div className="flex-1 space-y-1">
          <label className="text-sm font-medium text-slate-700">Name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            placeholder="e.g. Checking"
            className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium text-slate-700">Type</label>
          <select
            value={type}
            onChange={(e) => setType(e.target.value)}
            className="border border-slate-300 rounded-lg px-3 py-2 bg-white"
          >
            <option value="checking">Checking</option>
            <option value="savings">Savings</option>
            <option value="cash">Cash</option>
          </select>
        </div>
        <button
          type="submit"
          disabled={createMutation.isPending}
          className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white font-medium rounded-lg px-4 py-2"
        >
          Add account
        </button>
      </form>

      <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
        {accountsQuery.isLoading && <div className="p-5 text-slate-500">Loading…</div>}
        {accountsQuery.data && accountsQuery.data.length === 0 && (
          <div className="p-5 text-slate-500">No accounts yet. Add one above.</div>
        )}
        {accountsQuery.data && accountsQuery.data.length > 0 && (
          <table className="w-full text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr>
                <th className="text-left px-5 py-2">Name</th>
                <th className="text-left px-5 py-2">Type</th>
                <th className="text-right px-5 py-2">Balance</th>
              </tr>
            </thead>
            <tbody>
              {accountsQuery.data.map((a) => (
                <tr key={a.id} className="border-t border-slate-100">
                  <td className="px-5 py-3">
                    <Link to={`/accounts/${a.id}`} className="text-indigo-600 hover:underline">
                      {a.name}
                    </Link>
                  </td>
                  <td className="px-5 py-3 capitalize text-slate-600">{a.type}</td>
                  <td className="px-5 py-3 text-right tabular-nums">
                    {formatCents(a.balance_cents)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
