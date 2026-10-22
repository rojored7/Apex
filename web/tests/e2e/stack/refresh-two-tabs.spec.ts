// S2-F3 · US-043 contra el stack (proyecto `stack`, V4): dos pestañas del mismo navegador con
// el access vencido piden datos a la vez y ninguna pierde la sesión; el api ve un solo
// POST /auth/refresh (Web Locks `apex-refresh` + BroadcastChannel `apex-auth`), sin reuso.
// El vencimiento se fuerza respondiendo una vez 401 token_expired a la primera lectura de
// cada pestaña (el reloj del navegador no vence un JWT que valida el servidor). Necesita B1
// a B3. Sin E2E_BASE_URL se omite.
import { expect, test, type Page, type Route } from "@playwright/test";
import { loginComo } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;

async function vencerUnaVez(page: Page): Promise<void> {
  let pendiente = true;
  await page.route("**/api/v1/settings/gym", async (route: Route) => {
    if (!pendiente) {
      await route.continue();
      return;
    }
    pendiente = false;
    await route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "token_expired", message: "Token vencido" } }),
    });
  });
}

test.describe("refresh compartido entre pestañas contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con B1 a B3");

  test("dos pestañas con el access vencido hacen un solo refresh y siguen con sesión", async ({ page, context }) => {
    await loginComo(page);
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1, name: /Hola/ })).toBeVisible();
    const second = await context.newPage();
    await second.goto("/");
    await expect(second.getByRole("heading", { level: 1, name: /Hola/ })).toBeVisible();

    const refreshes: number[] = [];
    context.on("response", (response) => {
      if (response.url().endsWith("/api/v1/auth/refresh")) refreshes.push(response.status());
    });
    await vencerUnaVez(page);
    await vencerUnaVez(second);

    const menuLink = (p: Page) => p.getByRole("navigation", { name: "Menú principal" }).getByRole("link", { name: "Configuración" });
    await Promise.all([menuLink(page).click(), menuLink(second).click()]);

    for (const tab of [page, second]) {
      await expect(tab.getByRole("heading", { level: 1, name: /Configuración/ })).toBeVisible();
      await expect(tab.getByRole("textbox", { name: /Nombre/ })).toBeVisible();
    }
    expect(refreshes).toEqual([200]);

    await second.reload();
    await expect(second.getByRole("heading", { level: 1, name: /Configuración/ })).toBeVisible();
  });
});
