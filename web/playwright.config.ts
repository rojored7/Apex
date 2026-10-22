import { defineConfig, devices } from "@playwright/test";

// S2-W0-1: dos proyectos.
// - `preview`: el build servido por `vite preview` (sin api); lo arranca webServer.
// - `stack`: el stack de Compose (Nginx + api + db) en E2E_BASE_URL. Con esa variable no se
//   arranca ningún webServer: el stack ya está arriba (job e2e-stack de CI o 8180 local).
const PORT = 4173;
const PREVIEW_URL = `http://localhost:${String(PORT)}`;
const STACK_URL = process.env.E2E_BASE_URL?.replace(/\/+$/, "");

export default defineConfig({
  testDir: "tests/e2e",
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: "list",
  projects: [
    {
      name: "preview",
      testIgnore: ["stack/**", "helpers/**"],
      use: { ...devices["Desktop Chrome"], baseURL: PREVIEW_URL },
    },
    {
      name: "stack",
      testMatch: "stack/**/*.spec.ts",
      use: { ...devices["Desktop Chrome"], baseURL: STACK_URL ?? PREVIEW_URL },
    },
  ],
  ...(STACK_URL === undefined
    ? {
        webServer: {
          command: `npm run build && npm run preview -- --port ${String(PORT)} --strictPort`,
          port: PORT,
          reuseExistingServer: !process.env.CI,
          timeout: 180_000,
        },
      }
    : {}),
});
