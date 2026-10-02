import AsyncStorage from "@react-native-async-storage/async-storage";

import { forgetServerUrl, loadServerUrl, saveServerUrl, secureStoreTokenStore } from "./storage";

const TOKENS = { accessToken: "access-1", refreshToken: "refresh-1" };

describe("secureStoreTokenStore", () => {
  it("round-trips a session and clears it", async () => {
    await secureStoreTokenStore.write(TOKENS);
    await expect(secureStoreTokenStore.read()).resolves.toEqual(TOKENS);

    await secureStoreTokenStore.write(null);
    await expect(secureStoreTokenStore.read()).resolves.toBeNull();
  });
});

describe("loadServerUrl", () => {
  it("returns the saved server and keeps its session", async () => {
    await saveServerUrl("https://budget.example.com");
    await secureStoreTokenStore.write(TOKENS);

    await expect(loadServerUrl()).resolves.toBe("https://budget.example.com");
    await expect(secureStoreTokenStore.read()).resolves.toEqual(TOKENS);
  });

  it("drops tokens that survived an uninstall", async () => {
    // Keychain items outlive the app on iOS; AsyncStorage does not.
    await secureStoreTokenStore.write(TOKENS);

    await expect(loadServerUrl()).resolves.toBeNull();
    await expect(secureStoreTokenStore.read()).resolves.toBeNull();
  });

  it("forgets the server", async () => {
    await saveServerUrl("https://budget.example.com");
    await forgetServerUrl();

    await expect(AsyncStorage.getItem("zerobudget.server_url")).resolves.toBeNull();
  });
});
