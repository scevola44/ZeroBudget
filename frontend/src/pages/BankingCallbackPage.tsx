import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { bankingApi } from "../api/banking";
import type { CallbackResponse } from "../api/banking";

type CallbackState =
  | { phase: "working" }
  | { phase: "done"; result: CallbackResponse }
  | { phase: "failed"; message: string };

/** Landing page for the bank's redirect after the user authorizes access. */
export function BankingCallbackPage() {
  const [searchParams] = useSearchParams();
  const qc = useQueryClient();
  const [state, setState] = useState<CallbackState>({ phase: "working" });
  // React 18 StrictMode double-mounts effects; the callback code is
  // single-use at the provider, so guard against a second POST.
  const startedRef = useRef(false);

  const code = searchParams.get("code");
  const authState = searchParams.get("state");

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    if (!code || !authState) {
      const providerError = searchParams.get("error");
      setState({
        phase: "failed",
        message: providerError
          ? `The bank reported an error: ${providerError}`
          : "Missing authorization parameters in the redirect.",
      });
      return;
    }

    bankingApi
      .completeCallback(code, authState)
      .then((result) => {
        setState({ phase: "done", result });
        void qc.invalidateQueries({ queryKey: ["accounts"] });
        void qc.invalidateQueries({ queryKey: ["transactions"] });
        void qc.invalidateQueries({ queryKey: ["budget"] });
        void qc.invalidateQueries({ queryKey: ["bank-connections"] });
        void qc.invalidateQueries({ queryKey: ["sync-status"] });
      })
      .catch((err: unknown) => {
        setState({
          phase: "failed",
          message: err instanceof Error ? err.message : "Failed to complete the bank connection.",
        });
      });
  }, [code, authState, qc, searchParams]);

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold">Connecting your bank…</h1>

      {state.phase === "working" && (
        <div className="bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 rounded-2xl p-5 text-stone-600 dark:text-stone-400">
          Finalizing the connection and importing transactions. This can take a moment.
        </div>
      )}

      {state.phase === "done" && (
        <div className="bg-emerald-50 dark:bg-emerald-900/30 border border-emerald-200 dark:border-emerald-800 text-emerald-800 dark:text-emerald-200 rounded-xl px-4 py-3 text-sm space-y-1">
          <div>
            Connected {state.result.connection.aspsp_name} · linked{" "}
            {state.result.account_ids.length} account(s) · imported {state.result.sync.added}{" "}
            transaction(s).
          </div>
          {state.result.skipped_accounts.length > 0 && (
            <div>
              Skipped {state.result.skipped_accounts.length} account(s):{" "}
              {state.result.skipped_accounts.map((s) => `${s.name} (${s.reason})`).join(", ")}
            </div>
          )}
        </div>
      )}

      {state.phase === "failed" && (
        <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-800 dark:text-red-200 rounded-xl px-4 py-3 text-sm">
          {state.message}
        </div>
      )}

      {state.phase !== "working" && (
        <Link
          to="/accounts"
          className="inline-block bg-indigo-600 hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600 text-white font-medium rounded-lg px-4 py-2"
        >
          Back to accounts
        </Link>
      )}
    </div>
  );
}
