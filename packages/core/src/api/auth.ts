import type { components } from "../generated/schema";
import { api, getTokenStore } from "./client";

type TokenResponse = components["schemas"]["TokenResponse"];

async function startSession(response: TokenResponse): Promise<void> {
  await getTokenStore().write({
    accessToken: response.access_token,
    refreshToken: response.refresh_token,
  });
}

export async function login(email: string, password: string): Promise<void> {
  await startSession(await api<TokenResponse>("/api/auth/login", { method: "POST", body: { email, password } }));
}

export async function register(email: string, password: string): Promise<void> {
  await startSession(await api<TokenResponse>("/api/auth/register", { method: "POST", body: { email, password } }));
}

export async function hasStoredSession(): Promise<boolean> {
  return (await getTokenStore().read()) !== null;
}

/** Clears the local session first so sign-out never depends on the network. */
export async function logout(): Promise<void> {
  const tokenStore = getTokenStore();
  const tokens = await tokenStore.read();
  await tokenStore.write(null);
  if (!tokens) return;
  try {
    await api<void>("/api/auth/logout", { method: "POST", body: { refresh_token: tokens.refreshToken } });
  } catch {
    // Best effort: the server-side session just lives until its refresh token expires.
  }
}
