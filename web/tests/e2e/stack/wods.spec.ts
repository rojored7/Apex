// S8-F2 (US-166, US-167, S8-D7, S8-D8) contra el stack de Compose: /wods muestra la semana (no «No encontrada», lección de
// S7-D43), /wods/nuevo crea «Fran» con benchmark en una fecha única por corrida y lo ve en el calendario, y /wods/:id/editar
// abre con los datos guardados. Sin E2E_BASE_URL se omite. Necesita `seed-benchmarks` (Fran) y al menos un movimiento activo.
// Idempotente: la fecha sale de la marca de la corrida (un día de 2031); el api no tiene DELETE de WODs (S8-D7).
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { diaLibreDeWod, esperarTransiciones, loginComo, semanaIso } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const FIRST_DAY = Date.UTC(2031, 0, 1);

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

test.describe("WODs contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con A3; en preview no hay api");

  test("/wods muestra la semana actual", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loginComo(page);
    await page.goto("/wods");
    await expect(page.getByRole("heading", { level: 1, name: "WODs" })).toBeVisible();
    await expect(page.getByText("No encontrada")).toHaveCount(0);
    await expect(page.getByRole("list", { name: "Semana" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Semana siguiente" })).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);
  });

  test("/wods/nuevo crea «Fran» con benchmark, lo ve en el calendario y /wods/:id/editar abre con los datos", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loginComo(page);
    const DATE = await diaLibreDeWod(page, FIRST_DAY);
    await page.goto(`/wods/nuevo?date=${DATE}`);
    await expect(page.getByRole("heading", { level: 1, name: "Nuevo WOD" })).toBeVisible();
    await expect(page.getByLabel(/Fecha/)).toHaveValue(DATE);

    await page.getByLabel(/Título/).fill("Fran");
    await page.getByLabel(/Benchmark/).selectOption({ label: "Fran" });
    await expect(page.getByLabel(/Tipo de marca/)).toBeDisabled();
    const picker = page.getByRole("combobox", { name: "Agregar movimiento" });
    await picker.selectOption({ index: 1 });
    await page.getByRole("button", { name: "Agregar" }).click();
    await page.getByLabel(/^Repeticiones de /).fill("21-15-9");
    expect(await axeViolations(page)).toEqual([]);
    await page.getByRole("button", { name: "Crear WOD" }).click();

    await expect(page).toHaveURL(/\/wods\/[0-9a-f-]{36}$/);
    const id = page.url().split("/").pop() ?? "";

    await page.goto(`/wods?semana=${semanaIso(DATE)}`);
    await expect(page.getByRole("link", { name: /^Fran, / })).toBeVisible();

    await page.goto(`/wods/${id}/editar`);
    await expect(page.getByRole("heading", { level: 1, name: "Editar WOD" })).toBeVisible();
    await expect(page.getByLabel(/Título/)).toHaveValue("Fran");
    await expect(page.getByLabel(/^Repeticiones de /)).toHaveValue("21-15-9");
  });
});
