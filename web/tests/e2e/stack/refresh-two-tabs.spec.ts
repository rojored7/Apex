// S2-F3 · US-043 contra el stack (proyecto `stack`, V4): dos pestañas del mismo navegador con
// el access vencido piden datos a la vez y ninguna pierde la sesión; el api ve un solo
// POST /auth/refresh (Web Locks `apex-refresh` + BroadcastChannel `apex-auth`), sin reuso.
// El vencimiento se fuerza respondiendo una vez 401 token_expired a la primera lectura de
// cada pestaña (el reloj del navegador no vence un JWT que valida el servidor). Necesita B1
// a B3. Sin E2E_BASE_URL se omite.
// V4 del Sprint 3: los dos 401 falsos se retienen hasta que lleguen las dos lecturas (barrera).
// Sin ella, si una pestaña salía tarde ya con el access nuevo que publicó la otra, el 401 falso
// "vencía" un token recién emitido y la app pedía un segundo refresh legítimo (1 de 3 corridas).
import { expect, test, type Page, type Route } from "@playwright/test";
import { loginComo } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;

/** Barrera de `n` llegadas: cada una espera hasta que hayan llegado todas. */
function barrera(n: number): () => Promise<void> {
  let llegadas = 0;
  let abrir: () => void = () => undefined;
  const abierta = new Promise<void>((resolve) => {
    abrir = resolve;
  });
  return async () => {
    llegadas += 1;
    if (llegadas === n) abrir();
    await abierta;
  };
}

async function vencerUnaVez(page: Page, esperarALasDemas: () => Promise<void>): Promise<void> {
  let pendiente = true;
  await page.route("**/api/v1/settings/gym", async (route: Route) => {
    if (!pendiente) {
      await route.continue();
      return;
    }
    pendiente = false;
    await esperarALasDemas();
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
    const esperarALasDemas = barrera(2);
    await vencerUnaVez(page, esperarALasDemas);
    await vencerUnaVez(second, esperarALasDemas);

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
