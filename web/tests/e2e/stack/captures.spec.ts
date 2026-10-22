// S2-W0-1 (US-068 DevOps): el build servido por Nginx en el stack carga en los cuatro anchos
// y en los dos temas; cada combinación deja su captura en test-results/captures/, que el job
// e2e-stack de CI sube como artefacto.
// V4 del Sprint 2: desde S2-F3 `/` sin sesión lleva a /login (ya no hay página estática con
// el h1 "APEX"); se capturan las dos pantallas reales: el login sin sesión y el Inicio del
// panel con la sesión del admin.
import { expect, test, type Page } from "@playwright/test";
import { THEMES, VIEWPORTS, capture, loginComo, type Theme } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;

// El panel es claro por defecto y recuerda la elección en localStorage (core/theme, DESIGN.md
// "Temas"); prefers-color-scheme solo no lo oscurece. La captura fija la elección como lo haría
// el botón de tema, antes de que cargue la app.
async function elegirTema(page: Page, theme: Theme): Promise<void> {
  await page.addInitScript((value) => {
    window.localStorage.setItem("apex.theme", value);
  }, theme);
}

test("el documento llega de Nginx con la CSP y la Referrer-Policy del stack", async ({ page }) => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL); vite preview no envía cabeceras");
  const response = await page.goto("/");
  const headers = response?.headers() ?? {};
  expect(headers["content-security-policy"]).toMatch(/script-src 'self' 'nonce-[0-9a-f]{32}'/);
  expect(headers["content-security-policy"]).toContain("form-action 'self'");
  expect(headers["referrer-policy"]).toBe("no-referrer");
});

// Las pantallas de acceso fuerzan el claro (AccessLayout, useForcedTheme("light"); DESIGN.md
// "Logo": wordmark negro en el login): aunque el usuario haya elegido oscuro, el login sale claro.
for (const width of VIEWPORTS) {
  test(`login a ${String(width)} px (siempre claro aunque se elija oscuro)`, async ({ page }) => {
    test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL)");
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ colorScheme: "dark" });
    await elegirTema(page, "dark");
    await page.goto("/");
    // RequireAuth conserva el destino: `/` sin sesión va a /login?next=%2F.
    await expect(page).toHaveURL(/\/login\?next=%2F$/);
    await expect(page.getByRole("heading", { level: 1, name: "Iniciar sesión" })).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    await capture(page, "login", "light", width);
  });
}

for (const theme of THEMES) {
  for (const width of VIEWPORTS) {
    test(`inicio en ${theme} a ${String(width)} px`, async ({ page }) => {
      test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con el login real");
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ colorScheme: theme });
      await elegirTema(page, theme);
      await loginComo(page);
      await page.goto("/");
      await expect(page.getByRole("heading", { level: 1, name: /Hola/ })).toBeVisible();
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow).toBeLessThanOrEqual(0);
      await capture(page, "inicio", theme, width);
    });
  }
}
