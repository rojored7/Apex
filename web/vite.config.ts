import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const page = (file: string): string => fileURLToPath(new URL(file, import.meta.url));

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  // US-038: cada <script> y <link> del build lleva nonce="__CSP_NONCE__"; Nginx lo
  // reemplaza por $request_id con sub_filter. El polyfill de modulepreload inyecta un
  // script en línea, incompatible con la CSP.
  html: { cspNonce: "__CSP_NONCE__" },
  build: {
    modulePreload: { polyfill: false },
    // US-068 T5: catalog.html (layouts y kit de muestra) solo entra con
    // `vite build --mode catalog`; el build de producción y la imagen de Nginx no lo llevan.
    rollupOptions: {
      input: mode === "catalog" ? { main: page("./index.html"), catalog: page("./catalog.html") } : { main: page("./index.html") },
    },
  },
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
      // main.tsx y dev/catalogMain.tsx solo montan la app en el navegador; los cubre Playwright.
      exclude: ["src/**/*.test.{ts,tsx}", "src/test/**", "src/main.tsx", "src/dev/catalogMain.tsx", "src/**/*.d.ts"],
      thresholds: {
        lines: 80,
        functions: 80,
        branches: 80,
        statements: 80,
        "src/shared/ui/**": { lines: 80, functions: 80, branches: 80, statements: 80 },
      },
    },
  },
}));
