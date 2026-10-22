// US-062 T8: portal a 320 y 390 × 844, tablet del box a 1024 × 768 y TV a 1920 × 1080,
// sin desborde ni barras de desplazamiento. Corre contra `vite preview` sobre catalog.html.
import { expect, test, type Page } from "@playwright/test";

async function overflow(page: Page): Promise<{ x: boolean; y: boolean }> {
  return page.evaluate(() => {
    const el = document.documentElement;
    return { x: el.scrollWidth > el.clientWidth, y: el.scrollHeight > el.clientHeight };
  });
}

for (const scheme of ["light", "dark"] as const) {
  for (const size of [
    { width: 320, height: 640 },
    { width: 390, height: 844 },
  ]) {
    test(`portal en ${scheme} a ${String(size.width)} × ${String(size.height)}`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.setViewportSize(size);
      await page.goto("/catalog.html?vista=portal");

      const nav = page.getByRole("navigation", { name: "Menú del portal" });
      await expect(nav.getByRole("link")).toHaveText(["Inicio", "Pagos", "WODs", "Progreso", "Yo"]);
      await expect(page.locator("html")).not.toHaveAttribute("data-theme", /.+/);
      expect((await overflow(page)).x).toBe(false);

      for (const link of await nav.getByRole("link").all()) {
        expect((await link.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44);
      }
      await page.getByText("Último bloque del contenido").scrollIntoViewIfNeeded();
      await page.evaluate(() => {
        window.scrollTo(0, document.documentElement.scrollHeight);
      });
      const last = await page.getByText("Último bloque del contenido").boundingBox();
      const navBox = await nav.boundingBox();
      expect((last?.y ?? 0) + (last?.height ?? 0)).toBeLessThanOrEqual(navBox?.y ?? 0);
      await page.screenshot({ path: `test-results/captures/portal-${scheme}-${String(size.width)}.png` });
    });
  }
}

test("tablet del box en oscuro aunque el sistema prefiera claro, con controles de 56 px", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.goto("/catalog.html?vista=gym");

  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  for (const control of await page.getByRole("main").getByRole("button").all()) {
    expect((await control.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(56);
  }
  expect((await page.getByRole("link", { name: "Clases" }).boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(56);
  expect(await overflow(page)).toEqual({ x: false, y: false });
  await page.screenshot({ path: "test-results/captures/gym-dark-1024.png" });
});

test("TV a 1920 × 1080 sin barras, sin cursor y sin foco", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/catalog.html?vista=tv");

  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.getByText("WOD del día")).toBeVisible();
  expect(await overflow(page)).toEqual({ x: false, y: false });
  const cursor = await page.getByTestId("tv-stage").evaluate((el) => getComputedStyle(el).cursor);
  expect(cursor).toBe("none");

  for (let i = 0; i < 3; i += 1) {
    await page.keyboard.press("Tab");
    expect(await page.evaluate(() => document.activeElement === document.body)).toBe(true);
  }
  await page.screenshot({ path: "test-results/captures/tv-dark-1920.png" });
});

test("TV en una pantalla de 1280 × 720 escala sin desbordar", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto("/catalog.html?vista=tv");

  await expect(page.getByText("WOD del día")).toBeVisible();
  expect(await overflow(page)).toEqual({ x: false, y: false });
});
