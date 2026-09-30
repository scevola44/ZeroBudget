import type { AuthTokens, TokenStore } from "@zerobudget/core";

// The access-token key predates refresh tokens, so it keeps its original name.
const ACCESS_TOKEN_KEY = "zerobudget.token";
const REFRESH_TOKEN_KEY = "zerobudget.refresh_token";

export const localStorageTokenStore: TokenStore = {
  // A session from before refresh tokens existed has no refresh token, so it
  // reads as signed out and the user logs in once more.
  async read(): Promise<AuthTokens | null> {
    const accessToken = localStorage.getItem(ACCESS_TOKEN_KEY);
    const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
    return accessToken && refreshToken ? { accessToken, refreshToken } : null;
  },

  async write(tokens: AuthTokens | null): Promise<void> {
    if (tokens) {
      localStorage.setItem(ACCESS_TOKEN_KEY, tokens.accessToken);
      localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refreshToken);
    } else {
      localStorage.removeItem(ACCESS_TOKEN_KEY);
      localStorage.removeItem(REFRESH_TOKEN_KEY);
    }
  },
};
