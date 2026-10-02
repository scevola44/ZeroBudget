import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import {
  api,
  hasStoredSession,
  login as loginRequest,
  logout as logoutRequest,
  register as registerRequest,
  subscribeToSessionExpiry,
  type User,
} from "@zerobudget/core";

import { useConnection } from "../connection/ConnectionContext";

/**
 * `unreachable` means a stored session exists but the server couldn't be
 * asked about it (offline, server down). Unlike the web app, a phone is
 * routinely offline at launch, and treating that as signed-out would throw
 * away a 90-day session the server still honours.
 */
export type SessionStatus = "loading" | "signedOut" | "signedIn" | "unreachable";

type AuthState = {
  status: SessionStatus;
  user: User | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  /** Asks the server again after `unreachable`. */
  retry: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

// Mirrors frontend/src/auth/AuthContext.tsx; a second copy is cheaper than a
// shared abstraction until a third client needs it.
export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const { serverUrl, loading: connectionLoading } = useConnection();
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<SessionStatus>("loading");

  const loadMe = useCallback(async () => {
    if (!serverUrl || !(await hasStoredSession())) {
      setUser(null);
      setStatus("signedOut");
      return;
    }
    try {
      setUser(await api<User>("/api/auth/me"));
      setStatus("signedIn");
    } catch {
      // The client already cleared the session if the server rejected it, so
      // a session that is still stored means the server just couldn't answer.
      setUser(null);
      setStatus((await hasStoredSession()) ? "unreachable" : "signedOut");
    }
  }, [serverUrl]);

  useEffect(() => {
    // Until the stored server is known, "no server" would read as signed out
    // and briefly route a signed-in user to the sign-in screen.
    if (!connectionLoading) void loadMe();
  }, [connectionLoading, loadMe]);

  const clearSessionState = useCallback(() => {
    setUser(null);
    setStatus("signedOut");
    // Cached responses belong to the account that just left.
    queryClient.clear();
  }, [queryClient]);

  useEffect(() => subscribeToSessionExpiry(clearSessionState), [clearSessionState]);

  const login = useCallback(
    async (email: string, password: string) => {
      await loginRequest(email, password);
      await loadMe();
    },
    [loadMe],
  );

  const register = useCallback(
    async (email: string, password: string) => {
      await registerRequest(email, password);
      await loadMe();
    },
    [loadMe],
  );

  const logout = useCallback(() => {
    clearSessionState();
    void logoutRequest();
  }, [clearSessionState]);

  const value = useMemo<AuthState>(
    () => ({ status, user, login, register, logout, retry: loadMe }),
    [status, user, login, register, logout, loadMe],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
