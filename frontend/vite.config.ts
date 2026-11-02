/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The app only ever calls relative `/api/...`. In dev, Vite forwards that to the backend; in the container,
// nginx does the same job (see nginx/default.conf.template), so no environment-specific URL is baked into the bundle.
const apiTarget = process.env.API_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: { "/api": { target: apiTarget, changeOrigin: true } },
  },
  preview: { port: 4173 },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    restoreMocks: true,
    coverage: {
      provider: "v8",
      include: ["src/**"],
      // Test helpers and the bootstrap file are not product code; main.tsx is exercised by the e2e projects.
      exclude: ["src/**/*.test.{ts,tsx}", "src/test/**", "src/main.tsx"],
      reporter: ["text", "lcov"],
      // Set just below current values (rounded down to a multiple of 5) so coverage can only ratchet up.
      thresholds: { lines: 95, branches: 75, functions: 95, statements: 90 },
    },
  },
});
