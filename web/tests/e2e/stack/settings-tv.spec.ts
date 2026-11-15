// S8-F5 (US-175, S8-D32, L-4) contra el stack de Compose: /sistema/configuracion?tab=tv regenera el token del admin y muestra el enlace
// con `#token=` una sola vez; al pulsar «Listo» ya no está. No imprime ni guarda el token. Sin E2E_BASE_URL se omite.
// Cambia el token de la TV del ensayo: la pantalla abierta con el anterior queda en «Token inválido» (es el comportamiento que prueba F6).
// Al terminar deja la TV como estaba: restaura refresco y ranking y revoca el token que generó (restaurarTv, en finally).
// ESCRITO, SIN CORRER: el stack de desarrollo está roto y su reparación espera al usuario (Sprint 8, F5).
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { esperarTransiciones, leerEstadoTv, loginComo, restaurarTv, sameOriginHeaders } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

test.describe("Pestaña Pantalla de TV de Configuración contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con C1; en preview no hay api");

  test("regenera el token y muestra el enlace con #token= una sola vez", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const adminToken = await loginComo(page);
    const headers = { Authorization: `Bearer ${adminToken}`, ...sameOriginHeaders() };
    const antes = await leerEstadoTv(page, headers);
    try {
      await page.goto("/sistema/configuracion?tab=tv");

      await expect(page.getByRole("heading", { level: 2, name: "Pantalla de TV" })).toBeVisible();
      await page.getByRole("button", { name: "Generar enlace nuevo" }).click();
      await page.getByRole("dialog").getByRole("button", { name: "Generar enlace" }).click();

      const enlace = page.getByRole("textbox", { name: "Enlace de la TV" });
      await expect(enlace).toBeVisible();
      expect(await enlace.inputValue()).toMatch(/\/tv#token=[A-Za-z0-9_-]{20,}$/);
      await expect(page.getByText(/Token activo/)).toBeVisible();
      expect(await axeViolations(page)).toEqual([]);

      await page.getByRole("button", { name: "Listo" }).click();
      await expect(enlace).toHaveCount(0);
      await page.reload();
      await expect(page.getByRole("textbox", { name: "Enlace de la TV" })).toHaveCount(0);
    } finally {
      await restaurarTv(page, headers, antes);
    }
  });
});
