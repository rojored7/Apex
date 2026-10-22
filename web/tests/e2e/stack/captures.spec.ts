// S2-W0-1 (US-068 DevOps): el build servido por Nginx en el stack carga en los cuatro anchos
// y en los dos temas; cada combinación deja su captura en test-results/captures/, que el job
// e2e-stack de CI sube como artefacto. Las pantallas reales (login, panel) se suman aquí a
// medida que llegan sus slices.
import { expect, test } from "@playwright/test";
import { THEMES, VIEWPORTS, capture } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;

test("el documento llega de Nginx con la CSP y la Referrer-Policy del stack", async ({ page }) => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL); vite preview no envía cabeceras");
  const response = await page.goto("/");
  const headers = response?.headers() ?? {};
  expect(headers["content-security-policy"]).toMatch(/script-src 'self' 'nonce-[0-9a-f]{32}'/);
  expect(headers["content-security-policy"]).toContain("form-action 'self'");
  expect(headers["referrer-policy"]).toBe("no-referrer");
});

for (const theme of THEMES) {
  for (const width of VIEWPORTS) {
    test(`inicio en ${theme} a ${String(width)} px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ colorScheme: theme });
      await page.goto("/");
      await expect(page.getByRole("heading", { level: 1, name: "APEX" })).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow).toBeLessThanOrEqual(0);
      await capture(page, "inicio", theme, width);
    });
  }
}
