import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The browser calls the API on its own origin; the dev and preview servers proxy /api to it,
// as nginx does in the container. INTENT_API_ORIGIN points the proxy at a different API port.
const api = process.env.INTENT_API_ORIGIN ?? "http://127.0.0.1:8000";
const proxy = { "/api": { target: api, changeOrigin: false } };

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: { host: "127.0.0.1", port: 5173, strictPort: true, proxy },
  preview: { host: "127.0.0.1", port: 4173, proxy },
  build: { sourcemap: true },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    restoreMocks: true,
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/**/*.test.{ts,tsx}",
        "src/test/**",
        "src/main.tsx",
        // Unmodified shadcn/ui output; customized components are tested through the features using them.
        "src/design-system/ui/**",
      ],
      reporter: ["text", "json-summary"],
      thresholds: { statements: 85, lines: 85, functions: 85, branches: 80 },
    },
  },
});
