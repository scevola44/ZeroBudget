import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { configureApiClient } from "@zerobudget/core";

import App from "./App";
import { AuthProvider } from "./auth/AuthContext";
import { localStorageTokenStore } from "./auth/localStorageTokenStore";
import "./index.css";

// Same-origin: the backend serves this bundle (Vite proxies /api in dev).
configureApiClient({ tokenStore: localStorageTokenStore });

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
