// S9-F1 (US-178, US-179, US-184; H-1, L-7) contra el stack de Compose: la pestaña Atleta de la ficha.
// - Un socio ficticio recién creado CON autorización de datos abre la pestaña Atleta (Resumen por defecto, sin «No encontrada»).
// - Registra una medición desde «Registrar medidas», revela el peso (61,2 kg) y lo ve; ningún valor llega en la lista.
// - `?tab=medidas` se conserva al recargar y abrir la pestaña NO pide ninguna vez `/reveal` (solo el clic en «Mostrar peso»).
// Sin E2E_BASE_URL se omite. ESCRITO POR EL ROJO: la ejecuta el orquestador contra el stack (P-E2E), no el agente de pruebas.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { crearSocio, darDeBajaSocio, esperarTransiciones, loginComo, type SocioCreado } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const WEIGHT_KG = "61,2";

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

test.describe("Pestaña Atleta de la ficha contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con A3 y C2; en preview no hay api");

  const socios: SocioCreado[] = [];
  test.afterEach(async ({ page }) => {
    for (const socio of socios.splice(0)) await darDeBajaSocio(page, socio.id);
  });

  test("abre la ficha y la pestaña Atleta, registra una medición, revela el peso y lo ve", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loginComo(page);
    const socio = await crearSocio(page);
    socios.push(socio);
    const reveals: string[] = [];
    page.on("request", (request) => {
      if (request.method() === "POST" && request.url().includes("/reveal")) reveals.push(request.url());
    });

    await page.goto(`/socios/${socio.id}`);
    await page.getByRole("tab", { name: "Atleta" }).click();
    await expect(page.getByText("No encontrada")).toHaveCount(0);
    await expect(page).toHaveURL(new RegExp(`/socios/${socio.id}/atleta`));
    await expect(page.getByRole("tab", { name: "Resumen" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("heading", { level: 2, name: "Medidas corporales" })).toBeVisible();
    await expect(page.getByText("Todavía no hay medidas registradas.")).toBeVisible();

    await page.getByRole("button", { name: /Registrar medidas/ }).click();
    const panel = page.getByRole("dialog", { name: "Registrar medidas" });
    await panel.getByLabel(/^Peso/).fill(WEIGHT_KG);
    await panel.getByRole("button", { name: "Guardar medidas" }).click();
    await expect(panel).toBeHidden();

    await page.getByRole("tab", { name: "Medidas corporales" }).click();
    await expect(page).toHaveURL(/tab=medidas/);
    const table = page.getByRole("table", { name: "Medidas corporales del socio" });
    await expect(table).toBeVisible();
    await expect(table.getByRole("button", { name: "Mostrar peso" })).toBeVisible();
    await expect(table).not.toContainText(WEIGHT_KG);
    expect(reveals).toEqual([]);

    await table.getByRole("button", { name: "Mostrar peso" }).click();
    await expect(table.getByText(`${WEIGHT_KG} kg`)).toBeVisible();
    expect(reveals).toHaveLength(1);
    expect(decodeURIComponent(page.url())).not.toContain(WEIGHT_KG);
    expect(await axeViolations(page)).toEqual([]);
  });

  test("?tab=medidas se conserva al recargar y abrir la pestaña no pide ningún reveal", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loginComo(page);
    const socio = await crearSocio(page);
    socios.push(socio);
    const reveals: string[] = [];
    page.on("request", (request) => {
      if (request.url().includes("/reveal")) reveals.push(request.url());
    });

    await page.goto(`/socios/${socio.id}/atleta?tab=medidas`);
    await expect(page.getByRole("tab", { name: "Medidas corporales" })).toHaveAttribute("aria-selected", "true");
    await page.reload();

    await expect(page).toHaveURL(/tab=medidas/);
    await expect(page.getByRole("tab", { name: "Medidas corporales" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByText("Todavía no hay medidas registradas. Usa «Registrar medidas» para guardar la primera.")).toBeVisible();
    expect(reveals).toEqual([]);
  });
});
