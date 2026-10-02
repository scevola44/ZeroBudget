import AsyncStorage from "@react-native-async-storage/async-storage";
import * as SecureStore from "expo-secure-store";

import type { AuthTokens, TokenStore } from "@zerobudget/core";

const ACCESS_TOKEN_KEY = "zerobudget.access_token";
const REFRESH_TOKEN_KEY = "zerobudget.refresh_token";
const SERVER_URL_KEY = "zerobudget.server_url";

export const secureStoreTokenStore: TokenStore = {
  async read(): Promise<AuthTokens | null> {
    const [accessToken, refreshToken] = await Promise.all([
      SecureStore.getItemAsync(ACCESS_TOKEN_KEY),
      SecureStore.getItemAsync(REFRESH_TOKEN_KEY),
    ]);
    return accessToken && refreshToken ? { accessToken, refreshToken } : null;
  },

  async write(tokens: AuthTokens | null): Promise<void> {
    if (tokens) {
      await Promise.all([
        SecureStore.setItemAsync(ACCESS_TOKEN_KEY, tokens.accessToken),
        SecureStore.setItemAsync(REFRESH_TOKEN_KEY, tokens.refreshToken),
      ]);
    } else {
      await Promise.all([
        SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY),
        SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY),
      ]);
    }
  },
};

/**
 * The server this install connected to, or null on a fresh install.
 *
 * iOS keeps Keychain items after the app is deleted, so tokens can outlive
 * the install that stored them, while AsyncStorage is wiped on uninstall. A
 * missing URL therefore means "fresh install", and any surviving tokens are
 * cleared instead of silently signing the next install back in.
 */
export async function loadServerUrl(): Promise<string | null> {
  const serverUrl = await AsyncStorage.getItem(SERVER_URL_KEY);
  if (serverUrl === null) await secureStoreTokenStore.write(null);
  return serverUrl;
}

export function saveServerUrl(serverUrl: string): Promise<void> {
  return AsyncStorage.setItem(SERVER_URL_KEY, serverUrl);
}

export function forgetServerUrl(): Promise<void> {
  return AsyncStorage.removeItem(SERVER_URL_KEY);
}
