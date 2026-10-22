import { defineConfig, devices } from "@playwright/test";

const PORT = 4173;

export default defineConfig({
  testDir: "tests/e2e",
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: "list",
  use: {
    baseURL: `http://localhost:${String(PORT)}`,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  // build:catalog genera el mismo index.html de producción más catalog.html (layouts y kit
  // de muestra de US-061, US-062 y US-068), que solo existe para estas pruebas.
  webServer: {
    command: `npm run build:catalog && npm run preview -- --port ${String(PORT)} --strictPort`,
    port: PORT,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
});
