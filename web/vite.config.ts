import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}", "tests/**/*.test.{ts,tsx}"],
    exclude: ["node_modules", "dist", "tests/e2e/**"],
    css: { modules: { classNameStrategy: "non-scoped" } },
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      // main.tsx solo monta la app en el navegador; lo cubre el smoke de Playwright.
      exclude: ["src/**/*.test.{ts,tsx}", "src/test/**", "src/main.tsx", "src/**/*.d.ts"],
      thresholds: {
        lines: 80,
        functions: 80,
        branches: 80,
        statements: 80,
        "src/shared/ui/**": { lines: 80, functions: 80, branches: 80, statements: 80 },
      },
    },
  },
});
