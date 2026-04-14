import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev the FastAPI backend runs on :8000 and Vite proxies /api/* to it so
// the frontend can use relative URLs everywhere. In prod the backend serves
// the built bundle from the same origin, so the proxy is dev-only.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
