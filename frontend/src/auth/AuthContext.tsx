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

type AuthState = {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const loadMe = useCallback(async () => {
    if (!(await hasStoredSession())) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      setUser(await api<User>("/api/auth/me"));
    } catch {
      // A rejected session is already cleared by the client; anything else
      // (server down) leaves the stored session alone for the next attempt.
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadMe();
  }, [loadMe]);

  const clearSessionState = useCallback(() => {
    setUser(null);
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
    () => ({ user, loading, login, register, logout }),
    [user, loading, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
