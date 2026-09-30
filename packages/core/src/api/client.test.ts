import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { logout } from "./auth";
import {
  api,
  ApiError,
  configureApiClient,
  subscribeToSessionExpiry,
  type AuthTokens,
  type TokenStore,
} from "./client";

const BASE_URL = "https://budget.example.com";

function memoryTokenStore(initial: AuthTokens | null): TokenStore & { current: AuthTokens | null } {
  const store = {
    current: initial,
    read: async () => store.current,
    write: async (tokens: AuthTokens | null) => {
      store.current = tokens;
    },
  };
  return store;
}

function jsonResponse(status: number, body?: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), { status });
}

const EXPIRED: AuthTokens = { accessToken: "expired-access", refreshToken: "refresh-1" };

function renewedTokens() {
  return jsonResponse(200, { access_token: "fresh-access", refresh_token: "refresh-2", expires_in: 3600 });
}

describe("api client", () => {
  const fetchMock = vi.fn<typeof fetch>();
  let unsubscribe: () => void;
  let sessionExpired: ReturnType<typeof vi.fn>;

  function calls(pathSuffix: string) {
    return fetchMock.mock.calls.filter(([url]) => String(url).endsWith(pathSuffix));
  }

  function authorizationOf(call: Parameters<typeof fetch>): string | undefined {
    return (call[1]?.headers as Record<string, string>)["Authorization"];
  }

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    sessionExpired = vi.fn();
    unsubscribe = subscribeToSessionExpiry(sessionExpired);
  });

  afterEach(() => {
    unsubscribe();
    vi.unstubAllGlobals();
  });

  it("prefixes the configured base URL and sends the access token", async () => {
    configureApiClient({ tokenStore: memoryTokenStore(EXPIRED), baseUrl: `${BASE_URL}/` });
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { ok: true }));

    await api("/api/accounts");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE_URL}/api/accounts`);
    expect((init?.headers as Record<string, string>)["Authorization"]).toBe("Bearer expired-access");
  });

  it("is same-origin when no base URL is configured", async () => {
    configureApiClient({ tokenStore: memoryTokenStore(null) });
    fetchMock.mockResolvedValueOnce(jsonResponse(200, {}));

    await api("/api/accounts");

    expect(fetchMock.mock.calls[0][0]).toBe("/api/accounts");
  });

  it("surfaces the server's error detail", async () => {
    configureApiClient({ tokenStore: memoryTokenStore(null) });
    fetchMock.mockResolvedValueOnce(jsonResponse(409, { detail: "Email already registered" }));

    await expect(api("/api/auth/register")).rejects.toMatchObject({
      status: 409,
      message: "Email already registered",
    });
  });

  it("returns undefined for 204 responses", async () => {
    configureApiClient({ tokenStore: memoryTokenStore(null) });
    fetchMock.mockResolvedValueOnce(jsonResponse(204));

    await expect(api<void>("/api/accounts/1", { method: "DELETE" })).resolves.toBeUndefined();
  });

  describe("when the access token has expired", () => {
    it("refreshes once and retries the request with the new token", async () => {
      const store = memoryTokenStore(EXPIRED);
      configureApiClient({ tokenStore: store });
      fetchMock
        .mockResolvedValueOnce(jsonResponse(401, { detail: "Invalid or expired token" }))
        .mockResolvedValueOnce(renewedTokens())
        .mockResolvedValueOnce(jsonResponse(200, { id: 7 }));

      await expect(api("/api/accounts")).resolves.toEqual({ id: 7 });

      expect(JSON.parse(calls("/api/auth/refresh")[0][1]?.body as string)).toEqual({
        refresh_token: "refresh-1",
      });
      expect(authorizationOf(fetchMock.mock.calls[2])).toBe("Bearer fresh-access");
      expect(store.current).toEqual({ accessToken: "fresh-access", refreshToken: "refresh-2" });
      expect(sessionExpired).not.toHaveBeenCalled();
    });

    it("shares one refresh between concurrent requests", async () => {
      configureApiClient({ tokenStore: memoryTokenStore(EXPIRED) });
      fetchMock.mockImplementation(async (input, init) => {
        const url = String(input);
        if (url.endsWith("/api/auth/refresh")) return renewedTokens();
        const bearer = (init?.headers as Record<string, string>)["Authorization"];
        return bearer === "Bearer fresh-access" ? jsonResponse(200, { ok: true }) : jsonResponse(401);
      });

      await Promise.all([api("/api/accounts"), api("/api/budget/2026-09"), api("/api/scopes")]);

      expect(calls("/api/auth/refresh")).toHaveLength(1);
    });

    it("ends the session and reports 401 when the refresh token is rejected", async () => {
      const store = memoryTokenStore(EXPIRED);
      configureApiClient({ tokenStore: store });
      fetchMock
        .mockResolvedValueOnce(jsonResponse(401, { detail: "Invalid or expired token" }))
        .mockResolvedValueOnce(jsonResponse(401, { detail: "Invalid or expired refresh token" }));

      const failure = await api("/api/accounts").catch((error: unknown) => error);

      expect(failure).toBeInstanceOf(ApiError);
      expect((failure as ApiError).status).toBe(401);
      expect(store.current).toBeNull();
      expect(sessionExpired).toHaveBeenCalledTimes(1);
    });

    it("keeps the session when the refresh fails for a non-auth reason", async () => {
      const store = memoryTokenStore(EXPIRED);
      configureApiClient({ tokenStore: store });
      fetchMock
        .mockResolvedValueOnce(jsonResponse(401))
        .mockResolvedValueOnce(jsonResponse(503));

      await expect(api("/api/accounts")).rejects.toMatchObject({ status: 503 });

      expect(store.current).toEqual(EXPIRED);
      expect(sessionExpired).not.toHaveBeenCalled();
    });

    it("keeps the session when the network is down during the refresh", async () => {
      const store = memoryTokenStore(EXPIRED);
      configureApiClient({ tokenStore: store });
      fetchMock
        .mockResolvedValueOnce(jsonResponse(401))
        .mockRejectedValueOnce(new TypeError("Network request failed"));

      await expect(api("/api/accounts")).rejects.toBeInstanceOf(TypeError);

      expect(store.current).toEqual(EXPIRED);
      expect(sessionExpired).not.toHaveBeenCalled();
    });

    it("skips the refresh when another tab already rotated the tokens", async () => {
      const store = memoryTokenStore(EXPIRED);
      configureApiClient({ tokenStore: store });
      fetchMock.mockImplementationOnce(async () => {
        store.current = { accessToken: "other-tab-access", refreshToken: "other-tab-refresh" };
        return jsonResponse(401);
      });
      fetchMock.mockResolvedValueOnce(jsonResponse(200, { ok: true }));

      await api("/api/accounts");

      expect(calls("/api/auth/refresh")).toHaveLength(0);
      expect(authorizationOf(fetchMock.mock.calls[1])).toBe("Bearer other-tab-access");
    });

    it("ends the session when the retry is still unauthorized", async () => {
      const store = memoryTokenStore(EXPIRED);
      configureApiClient({ tokenStore: store });
      fetchMock
        .mockResolvedValueOnce(jsonResponse(401))
        .mockResolvedValueOnce(renewedTokens())
        .mockResolvedValueOnce(jsonResponse(401));

      await expect(api("/api/accounts")).rejects.toMatchObject({ status: 401 });

      expect(store.current).toBeNull();
      expect(sessionExpired).toHaveBeenCalledTimes(1);
    });
  });

  it("does not try to refresh a failed login", async () => {
    const store = memoryTokenStore(EXPIRED);
    configureApiClient({ tokenStore: store });
    fetchMock.mockResolvedValueOnce(jsonResponse(401, { detail: "Invalid email or password" }));

    await expect(
      api("/api/auth/login", { method: "POST", body: { email: "a@b.co", password: "x" } }),
    ).rejects.toMatchObject({ status: 401, message: "Invalid email or password" });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(store.current).toEqual(EXPIRED);
    expect(sessionExpired).not.toHaveBeenCalled();
  });

  it("does nothing special for a 401 when nobody is signed in", async () => {
    configureApiClient({ tokenStore: memoryTokenStore(null) });
    fetchMock.mockResolvedValueOnce(jsonResponse(401, { detail: "Not authenticated" }));

    await expect(api("/api/auth/me")).rejects.toMatchObject({ status: 401 });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(sessionExpired).not.toHaveBeenCalled();
  });

  describe("logout", () => {
    it("clears the local session and revokes the refresh token on the server", async () => {
      const store = memoryTokenStore(EXPIRED);
      configureApiClient({ tokenStore: store });
      fetchMock.mockResolvedValueOnce(jsonResponse(204));

      await logout();

      expect(store.current).toBeNull();
      expect(JSON.parse(calls("/api/auth/logout")[0][1]?.body as string)).toEqual({
        refresh_token: "refresh-1",
      });
    });

    it("still signs out locally when the server is unreachable", async () => {
      const store = memoryTokenStore(EXPIRED);
      configureApiClient({ tokenStore: store });
      fetchMock.mockRejectedValueOnce(new TypeError("Network request failed"));

      await expect(logout()).resolves.toBeUndefined();

      expect(store.current).toBeNull();
    });
  });
});
