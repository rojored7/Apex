// S8-F6 (US-177, S8-D20): configuración de la prueba de resistencia de la TV (tests/soak). Sirve el build de producción con
// `vite preview` (sin api: las respuestas las fija la spec con page.route) y corre una sola spec, sin reintentos. La corre el flujo
// nocturno (.github/workflows/nightly.yml, job tv-soak) y, a mano, `npm run soak`. No forma parte de `npm run e2e` ni de la CI de PR.
import { defineConfig, devices } from "@playwright/test";

const PORT = 4174;

export default defineConfig({
  testDir: "tests/soak",
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  timeout: 10 * 60_000,
  reporter: "list",
  use: { ...devices["Desktop Chrome"], baseURL: `http://localhost:${String(PORT)}` },
  webServer: {
    command: `npm run build && npm run preview -- --port ${String(PORT)} --strictPort`,
    port: PORT,
    reuseExistingServer: !process.env.CI,
    timeout: 240_000,
  },
});
