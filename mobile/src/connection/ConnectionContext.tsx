import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { configureApiClient, logout } from "@zerobudget/core";

import { forgetServerUrl, loadServerUrl, saveServerUrl, secureStoreTokenStore } from "./storage";

type ConnectionState = {
  /** Base URL of the ZeroBudget instance, or null until the user picks one. */
  serverUrl: string | null;
  loading: boolean;
  /** `serverUrl` must already be normalized and verified. */
  connect: (serverUrl: string) => Promise<void>;
  /** Signs out of the current server and forgets it. */
  disconnect: () => Promise<void>;
};

const ConnectionContext = createContext<ConnectionState | null>(null);

function pointApiClientAt(serverUrl: string): void {
  configureApiClient({ tokenStore: secureStoreTokenStore, baseUrl: serverUrl });
}

export function ConnectionProvider({ children }: { children: ReactNode }) {
  const [serverUrl, setServerUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      const stored = await loadServerUrl();
      if (stored) pointApiClientAt(stored);
      setServerUrl(stored);
      setLoading(false);
    })();
  }, []);

  const connect = useCallback(async (verifiedUrl: string) => {
    await saveServerUrl(verifiedUrl);
    // Before the state update, so nothing can render against the old server.
    pointApiClientAt(verifiedUrl);
    setServerUrl(verifiedUrl);
  }, []);

  const disconnect = useCallback(async () => {
    // Tokens belong to the server that issued them; never carry them to another.
    await logout();
    await forgetServerUrl();
    setServerUrl(null);
  }, []);

  const value = useMemo<ConnectionState>(
    () => ({ serverUrl, loading, connect, disconnect }),
    [serverUrl, loading, connect, disconnect],
  );

  return <ConnectionContext.Provider value={value}>{children}</ConnectionContext.Provider>;
}

export function useConnection(): ConnectionState {
  const ctx = useContext(ConnectionContext);
  if (!ctx) throw new Error("useConnection must be used inside <ConnectionProvider>");
  return ctx;
}
