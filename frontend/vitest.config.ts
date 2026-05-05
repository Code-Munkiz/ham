/**
 * Vitest config — Phase C.1 baseline.
 *
 * Reuses the same `@/` alias as `vite.config.ts` so test imports match prod.
 * jsdom is set globally even though our first round of tests is pure-function;
 * the cost is ~30ms per test file and keeps the door open for component
 * smoke tests later without per-file `// @vitest-environment` headers.
 */
import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    css: false,
    reporters: ["default"],
  },
});
