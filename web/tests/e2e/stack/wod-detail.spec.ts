// S8-F3 (US-171, US-172, E5) contra el stack de Compose: /wods/:id abre el WOD (no «No encontrada», lección de S7-D43), muestra el
// título y la tabla del leaderboard (vacía si aún no hay resultados) y la pestaña Historial del admin lee GET /audit.
// Sin E2E_BASE_URL se omite. Crea su propio WOD (fecha única por corrida, un día de 2032); el api no tiene DELETE de WODs.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { diaLibreDeWod, esperarTransiciones, loginComo } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const FIRST_DAY = Date.UTC(2032, 0, 1);

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

test.describe("Detalle de WOD contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con B4; en preview no hay api");

  test("/wods/:id muestra el título, el leaderboard y el historial", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loginComo(page);
    const DATE = await diaLibreDeWod(page, FIRST_DAY);
    await page.goto(`/wods/nuevo?date=${DATE}`);
    await page.getByLabel(/Título/).fill("Detalle E2E");
    await page.getByRole("combobox", { name: "Agregar movimiento" }).selectOption({ index: 1 });
    await page.getByRole("button", { name: "Agregar" }).click();
    await page.getByLabel(/^Repeticiones de /).fill("10");
    await page.getByRole("button", { name: "Crear WOD" }).click();

    await expect(page).toHaveURL(/\/wods\/[0-9a-f-]{36}$/);
    await expect(page.getByText("No encontrada")).toHaveCount(0);
    await expect(page.getByRole("heading", { level: 1, name: "Detalle E2E" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Leaderboard" })).toBeVisible();
    await expect(page.getByText(/Todavía no hay resultados|Atleta/).first()).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);

    await page.getByRole("tab", { name: "Historial" }).click();
    await expect(page.getByRole("heading", { name: "Historial" })).toBeVisible();
    await expect(page.getByText(/WOD · creó/).first()).toBeVisible();
  });
});
