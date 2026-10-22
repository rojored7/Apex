// S2-F5 (US-055, US-057, US-058) contra el stack de Compose (proyecto `stack`, V4 del plan):
// sesión real, api real y base real. Necesita B1 (configuración), B2/B3 (login, refresh y
// /auth/me) y B4 (POST /users para el coach). Sin E2E_BASE_URL se omite: la variante contra
// `vite preview` con el api simulado es ../settings-config.spec.ts.
// Idempotente: valores únicos por corrida (V4 corre las specs dos veces seguidas).
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { crearCoach, esperarTransiciones, loginComo } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const PATH = "/sistema/configuracion";
const RUN = Date.now().toString(36);
const GYM_NAME = `APEX CrossFit Bogotá ${RUN}`;
const NIT = "901234567-8";

test.describe("configuración del gimnasio contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con B1 a B4; en preview corre settings-config.spec.ts");
  test.describe.configure({ mode: "serial" });

  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
  });

  test("el admin guarda nombre y NIT, recarga y los ve", async ({ page }) => {
    await loginComo(page);
    await page.goto(PATH);

    await page.getByRole("textbox", { name: /Nombre/ }).fill(GYM_NAME);
    await page.getByRole("textbox", { name: "NIT" }).fill(NIT);
    await page.getByRole("button", { name: "Guardar" }).click();
    await expect(page.getByText("Cambios guardados")).toBeVisible();

    await page.reload();
    await expect(page.getByRole("textbox", { name: /Nombre/ })).toHaveValue(GYM_NAME);
    await expect(page.getByRole("textbox", { name: "NIT" })).toHaveValue(NIT);
  });

  test("el admin publica una versión nueva de la política de privacidad", async ({ page }) => {
    await loginComo(page);
    await page.goto(`${PATH}?tab=privacidad`);
    const version = `e2e-${RUN}`.slice(0, 20);

    await page.getByRole("textbox", { name: /Versión de la política/ }).fill(version);
    await page.getByRole("textbox", { name: /Texto de la política/ }).fill(`Autorizo el tratamiento de mis datos personales (corrida ${RUN}).`);
    await page.getByRole("button", { name: "Guardar" }).click();
    // Si ya había una versión publicada, la app pide confirmar la nueva.
    const dialog = page.getByRole("dialog", { name: `¿Publicar la versión ${version}?` });
    if (await dialog.isVisible().catch(() => false)) await dialog.getByRole("button", { name: "Publicar versión" }).click();
    await expect(page.getByText(new RegExp(`^Versión vigente: ${version} · vigente desde `))).toBeVisible();

    await page.reload();
    await expect(page.getByRole("textbox", { name: /Versión de la política/ })).toHaveValue(version);
  });

  test("el admin fija expiring_days = 7", async ({ page }) => {
    await loginComo(page);
    await page.goto(`${PATH}?tab=membresias`);
    const expiring = page.getByRole("spinbutton", { name: /Por vencer/ });

    await expiring.fill("7");
    await page.getByRole("button", { name: "Guardar" }).click();
    await expect(page.getByText("Cambios guardados")).toBeVisible();

    await page.reload();
    await expect(page.getByRole("spinbutton", { name: /Por vencer/ })).toHaveValue("7");
  });

  test("las tres pestañas pasan axe con datos reales", async ({ page }) => {
    await loginComo(page);
    for (const id of ["gimnasio", "privacidad", "membresias"]) {
      await page.goto(`${PATH}?tab=${id}`);
      await expect(page.getByRole("button", { name: "Guardar" })).toBeVisible();
      await esperarTransiciones(page);
      const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
      expect(result.violations.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
    }
  });

  test("el coach ve Sin permiso y su TopBar muestra el nombre del gimnasio", async ({ page, browser }) => {
    const coach = await crearCoach(page);
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const coachPage = await context.newPage();
    try {
      const coachToken = await loginComo(coachPage, coach);
      await coachPage.goto(PATH);

      await expect(coachPage.getByRole("heading", { level: 1, name: "Sin permiso" })).toBeVisible();
      await expect(coachPage.getByRole("banner")).toContainText(GYM_NAME);
      const nav = coachPage.getByRole("navigation", { name: "Menú principal" });
      await expect(nav.getByRole("link", { name: "Configuración" })).toHaveCount(0);
      // El api también lo rechaza: el front oculta, el servidor decide (RN-15).
      const direct = await coachPage.request.get("/api/v1/settings/gym", { headers: { Authorization: `Bearer ${coachToken}` } });
      expect(direct.status()).toBe(403);
    } finally {
      await context.close();
    }
  });
});
