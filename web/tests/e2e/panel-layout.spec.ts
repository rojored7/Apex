// US-061 T7: el marco del panel en 320, 768, 1024 y 1440 px, en claro y oscuro, sin
// desborde horizontal; menú por rol y cajón en celular. Corre contra `vite preview` sobre
// la página de muestra `catalog.html` (fuera del build de producción).
import { expect, test, type Page } from "@playwright/test";

const WIDTHS = [320, 768, 1024, 1440] as const;
const THEMES = ["light", "dark"] as const;
const SYSTEM_LABELS = ["Usuarios y roles", "Auditoría", "Llaves de cifrado", "Configuración"];

async function noHorizontalOverflow(page: Page): Promise<void> {
  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
}

for (const theme of THEMES) {
  for (const width of WIDTHS) {
    test(`panel en ${theme} a ${String(width)} px sin desborde`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(`/catalog.html?vista=panel&rol=admin&tema=${theme}`);

      await expect(page.getByRole("heading", { level: 1, name: "Socios" })).toBeVisible();
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      await expect(page.getByRole("banner")).toBeVisible();
      if (width < 768) await expect(page.getByRole("button", { name: "Abrir menú" })).toBeVisible();
      else await expect(page.getByRole("navigation", { name: "Menú principal" })).toBeVisible();
      await noHorizontalOverflow(page);
      await page.screenshot({ path: `test-results/captures/panel-${theme}-${String(width)}.png`, fullPage: true });
    });
  }
}

test("el coach no ve Planes ni Sistema; el admin sí", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/catalog.html?vista=panel&rol=coach");
  const coachNav = page.getByRole("navigation", { name: "Menú principal" });
  await expect(coachNav.getByRole("link", { name: "Socios" })).toBeVisible();
  await expect(coachNav.getByRole("link", { name: "Planes" })).toHaveCount(0);
  for (const label of SYSTEM_LABELS) await expect(coachNav.getByRole("link", { name: label })).toHaveCount(0);

  await page.goto("/catalog.html?vista=panel&rol=admin");
  const adminNav = page.getByRole("navigation", { name: "Menú principal" });
  await expect(adminNav.getByRole("link", { name: "Planes" })).toBeVisible();
  await expect(adminNav.getByRole("link", { name: "Usuarios y roles" })).toBeVisible();
});

test("la entrada activa lleva aria-current", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/catalog.html?vista=panel&rol=admin");

  await expect(page.getByRole("link", { name: "Socios" })).toHaveAttribute("aria-current", "page");
});

test("en celular el botón abre el cajón; Escape lo cierra y el foco vuelve", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/catalog.html?vista=panel&rol=coach");
  const button = page.getByRole("button", { name: "Abrir menú" });

  await button.click();
  const drawer = page.getByRole("dialog", { name: "Menú principal" });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByRole("link", { name: "Socios" })).toBeVisible();
  await expect(drawer.getByRole("link", { name: "Planes" })).toHaveCount(0);
  const box = await button.boundingBox();
  expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);

  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
  await expect(button).toBeFocused();
});

test("Saltar al contenido es el primer Tab y lleva el foco a main", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/catalog.html?vista=panel&rol=admin");

  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Saltar al contenido" });
  await expect(skip).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("main")).toBeFocused();
});
