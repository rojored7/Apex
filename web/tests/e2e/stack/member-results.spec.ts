// S8-F5 (US-173) contra el stack de Compose: /socios/:id/resultados abre la pestaña (no «No encontrada», lección de S7-D43) y un socio
// recién creado muestra «Todavía no tiene resultados» con el enlace a los WODs. Sin E2E_BASE_URL se omite.
// ESCRITO, SIN CORRER: el stack de desarrollo está roto y su reparación espera al usuario (Sprint 8, F5).
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { crearSocio, darDeBajaSocio, esperarTransiciones, loginComo, type SocioCreado } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

test.describe("Pestaña Resultados de la ficha contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con B4; en preview no hay api");

  const socios: SocioCreado[] = [];
  test.afterEach(async ({ page }) => {
    for (const socio of socios.splice(0)) await darDeBajaSocio(page, socio.id);
  });

  test("/socios/:id/resultados muestra el estado vacío de un socio nuevo", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loginComo(page);
    const socio = await crearSocio(page);
    socios.push(socio);

    await page.goto(`/socios/${socio.id}/resultados`);

    await expect(page.getByText("No encontrada")).toHaveCount(0);
    await expect(page.getByRole("tab", { name: "Resultados" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByText(/Todavía no tiene resultados/)).toBeVisible();
    await expect(page.getByRole("link", { name: "Ver los WODs" })).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);
  });
});
