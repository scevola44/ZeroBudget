import "../../global.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import { useEffect } from "react";

import { AuthProvider, useAuth } from "../auth/AuthContext";
import { ConnectionProvider, useConnection } from "../connection/ConnectionContext";

// Held until the stored server and session are known, so launch never
// flashes the onboarding or sign-in screen at someone who is signed in.
void SplashScreen.preventAutoHideAsync();

// Same defaults as the web app (frontend/src/main.tsx).
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      retry: 1,
    },
  },
});

export default function RootLayout() {
  return (
    <QueryClientProvider client={queryClient}>
      <ConnectionProvider>
        <AuthProvider>
          <StatusBar style="auto" />
          <RootNavigator />
        </AuthProvider>
      </ConnectionProvider>
    </QueryClientProvider>
  );
}

function RootNavigator() {
  const { serverUrl } = useConnection();
  const { status } = useAuth();
  const ready = status !== "loading";

  useEffect(() => {
    if (ready) void SplashScreen.hideAsync();
  }, [ready]);

  if (!ready) return null;

  const hasSession = status === "signedIn" || status === "unreachable";
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Protected guard={serverUrl === null}>
        <Stack.Screen name="server" />
      </Stack.Protected>
      <Stack.Protected guard={serverUrl !== null && !hasSession}>
        <Stack.Screen name="login" />
        <Stack.Screen name="register" />
      </Stack.Protected>
      <Stack.Protected guard={hasSession}>
        <Stack.Screen name="index" />
      </Stack.Protected>
    </Stack>
  );
}
