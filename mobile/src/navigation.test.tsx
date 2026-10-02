import AsyncStorage from "@react-native-async-storage/async-storage";
import { userEvent } from "@testing-library/react-native";
import { renderRouter, screen } from "expo-router/testing-library";

import { secureStoreTokenStore } from "./connection/storage";

const SERVER = "https://budget.example.com";
const APP_DIR = "./src/app";

type Route = { status: number; body: unknown };

/** Fakes the ZeroBudget API: each request path maps to a canned response. */
function serveApi(routes: Record<string, Route>) {
  const fetchMock = jest.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const match = Object.entries(routes).find(([path]) => url === `${SERVER}${path}`);
    if (!match) throw new TypeError(`Network request failed: ${url}`);
    return new Response(JSON.stringify(match[1].body), { status: match[1].status });
  });
  globalThis.fetch = fetchMock;
  return fetchMock;
}

const HEALTHY: Route = { status: 200, body: { status: "ok", service: "zerobudget", version: "1.0.0" } };
const ME: Route = { status: 200, body: { id: 1, email: "ada@example.com" } };
const SCOPES: Route = { status: 200, body: [{ id: 7, name: "Personal", sort_order: 0 }] };

function budgetFor(month: string, readyToAssignCents: number): Record<string, Route> {
  return {
    [`/api/budget/${month}`]: {
      status: 200,
      body: { month, ready_to_assign: [{ scope_id: 7, ready_to_assign_cents: readyToAssignCents }], groups: [] },
    },
  };
}

function thisMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

async function rememberServer() {
  await AsyncStorage.setItem("zerobudget.server_url", SERVER);
}

async function rememberSession() {
  await secureStoreTokenStore.write({ accessToken: "access-1", refreshToken: "refresh-1" });
}

describe("launch routing", () => {
  it("asks a fresh install for its server", async () => {
    serveApi({});

    await renderRouter(APP_DIR);

    expect(await screen.findByText("Connect to your server")).toBeOnTheScreen();
  });

  it("asks a known server's signed-out user to sign in", async () => {
    await rememberServer();
    serveApi({});

    await renderRouter(APP_DIR);

    expect(await screen.findByText("Sign in to ZeroBudget")).toBeOnTheScreen();
    expect(screen.getByText("budget.example.com")).toBeOnTheScreen();
  });

  it("resumes a stored session straight onto the home screen", async () => {
    await rememberServer();
    await rememberSession();
    serveApi({ "/api/auth/me": ME, "/api/scopes": SCOPES, ...budgetFor(thisMonth(), 123456) });

    await renderRouter(APP_DIR);

    expect(await screen.findByText("Signed in as ada@example.com")).toBeOnTheScreen();
    expect(await screen.findByText("€1,234.56")).toBeOnTheScreen();
    expect(screen.getByText("Ready to Assign — Personal")).toBeOnTheScreen();
  });

  it("keeps an offline user signed in rather than discarding the session", async () => {
    await rememberServer();
    await rememberSession();
    serveApi({});

    await renderRouter(APP_DIR);

    expect(await screen.findByText("Can't reach your server")).toBeOnTheScreen();
    await expect(secureStoreTokenStore.read()).resolves.not.toBeNull();
  });
});

describe("server onboarding", () => {
  it("refuses an http address until insecure servers are allowed", async () => {
    const fetchMock = serveApi({});
    const user = userEvent.setup();
    await renderRouter(APP_DIR);

    await user.type(await screen.findByLabelText("Server address"), "http://192.168.1.20:8000");
    await user.press(screen.getByRole("button", { name: "Connect" }));

    expect(await screen.findByText(/isn't using HTTPS/)).toBeOnTheScreen();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("remembers a verified server and moves on to sign-in", async () => {
    serveApi({ "/api/health": HEALTHY });
    const user = userEvent.setup();
    await renderRouter(APP_DIR);

    await user.type(await screen.findByLabelText("Server address"), "budget.example.com");
    await user.press(screen.getByRole("button", { name: "Connect" }));

    expect(await screen.findByText("Sign in to ZeroBudget")).toBeOnTheScreen();
    await expect(AsyncStorage.getItem("zerobudget.server_url")).resolves.toBe(SERVER);
  });
});
