// Tiny typed fetch wrapper. Centralizes base URL, auth header injection,
// silent token refresh and error handling so every API call in the app is a
// one-liner from a page. Platform specifics (where tokens are kept, which
// server to talk to) are injected once via `configureApiClient`.

export type AuthTokens = { accessToken: string; refreshToken: string };

/** Async because native secure storage (expo-secure-store) is. `write(null)` clears. */
export type TokenStore = {
  read: () => Promise<AuthTokens | null>;
  write: (tokens: AuthTokens | null) => Promise<void>;
};

type ApiClientConfig = {
  tokenStore: TokenStore;
  /** Prepended to every path. Empty means same-origin, which is what the web app wants. */
  baseUrl?: string;
};

type RefreshResponse = { access_token: string; refresh_token: string };

const REFRESH_PATH = "/api/auth/refresh";

// A 401 from these means "wrong credentials" or "dead refresh token", never
// "access token expired", so refreshing and retrying would be wrong (or loop).
const PATHS_THAT_NEVER_REFRESH = new Set([
  "/api/auth/login",
  "/api/auth/register",
  REFRESH_PATH,
  "/api/auth/logout",
]);

let config: { tokenStore: TokenStore; baseUrl: string } | null = null;
const sessionExpiryListeners = new Set<() => void>();
let refreshInFlight: Promise<boolean> | null = null;

export function configureApiClient({ tokenStore, baseUrl = "" }: ApiClientConfig): void {
  config = { tokenStore, baseUrl: baseUrl.replace(/\/+$/, "") };
}

function currentConfig() {
  if (!config) throw new Error("configureApiClient must be called before any API request");
  return config;
}

export function getTokenStore(): TokenStore {
  return currentConfig().tokenStore;
}

/** Called when the stored session can no longer be renewed, so the UI can sign out. */
export function subscribeToSessionExpiry(listener: () => void): () => void {
  sessionExpiryListeners.add(listener);
  return () => sessionExpiryListeners.delete(listener);
}

async function endSession(): Promise<void> {
  await currentConfig().tokenStore.write(null);
  sessionExpiryListeners.forEach((listener) => listener());
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type Options = {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
};

function send(path: string, opts: Options, accessToken: string | null): Promise<Response> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;

  return fetch(`${currentConfig().baseUrl}${path}`, {
    method: opts.method ?? "GET",
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
}

/**
 * True when the session now has a fresh access token, false when the server
 * rejected the refresh token (the session is then already ended). Any other
 * failure — network down, server error — throws and leaves the session alone,
 * so a blip doesn't discard a long-lived login.
 */
function refreshSession(refreshTokenThatFailed: string): Promise<boolean> {
  // Concurrent 401s share one refresh: refresh tokens are single-use, so a
  // second parallel attempt would look like a replay and revoke the session.
  refreshInFlight ??= exchangeRefreshToken(refreshTokenThatFailed).finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

async function exchangeRefreshToken(refreshTokenThatFailed: string): Promise<boolean> {
  const { tokenStore } = currentConfig();
  const current = await tokenStore.read();
  if (!current) return false;
  // Another tab already rotated it; retrying with what it stored is enough.
  // Two tabs refreshing in the same instant can still race and log both out —
  // accepted, the window is a single request round-trip.
  if (current.refreshToken !== refreshTokenThatFailed) return true;

  const res = await send(REFRESH_PATH, { method: "POST", body: { refresh_token: current.refreshToken } }, null);
  if (res.status === 401) {
    await endSession();
    return false;
  }
  if (!res.ok) throw new ApiError(res.status, `Request failed (${res.status})`);

  const renewed = (await res.json()) as RefreshResponse;
  await tokenStore.write({ accessToken: renewed.access_token, refreshToken: renewed.refresh_token });
  return true;
}

async function sendWithSession(path: string, opts: Options): Promise<Response> {
  const { tokenStore } = currentConfig();
  const tokens = await tokenStore.read();
  const res = await send(path, opts, tokens?.accessToken ?? null);

  if (res.status !== 401 || !tokens || PATHS_THAT_NEVER_REFRESH.has(path)) return res;
  if (!(await refreshSession(tokens.refreshToken))) return res;

  const retried = await send(path, opts, (await tokenStore.read())?.accessToken ?? null);
  if (retried.status === 401) await endSession();
  return retried;
}

export async function api<T>(path: string, opts: Options = {}): Promise<T> {
  const res = await sendWithSession(path, opts);

  if (res.status === 204) {
    return undefined as T;
  }

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body && typeof body.detail === "string") detail = body.detail;
    } catch {
      // ignore — fall through with generic message
    }
    throw new ApiError(res.status, detail);
  }

  return (await res.json()) as T;
}
