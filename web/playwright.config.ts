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
  webServer: {
    command: `npm run build && npm run preview -- --port ${String(PORT)} --strictPort`,
    port: PORT,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
});
