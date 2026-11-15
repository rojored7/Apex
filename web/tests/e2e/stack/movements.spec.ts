// S8-F1 (US-165, US-166, S8-D5, S8-D6) contra el stack de Compose: /movimientos abre la pantalla real (no «No
// encontrada», lección de S7-D43), el admin crea un movimiento con nombre único por corrida y lo ve en la lista,
// el mismo nombre en minúsculas da 409 bajo «Nombre», y ?tab=benchmarks muestra «Fran» tras `seed-benchmarks`.
// Sin E2E_BASE_URL se omite. Idempotente: el nombre lleva la marca de la corrida; el movimiento no se borra (el api no
// tiene DELETE, S8-D5) y la spec lo desactiva al terminar.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { esperarTransiciones, loginComo } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const NAME = `Movimiento E2E ${Date.now().toString(36)}`;

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

test.describe("movimientos y benchmarks contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con A1 y A2; en preview no hay api");

  test("el admin abre /movimientos, crea un movimiento y lo ve; el nombre repetido da 409", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loginComo(page);
    await page.goto("/movimientos");
    await expect(page.getByRole("heading", { level: 1, name: "Movimientos" })).toBeVisible();
    await expect(page.getByText("No encontrada")).toHaveCount(0);
    await expect(page.getByRole("tab", { name: "Movimientos", selected: true })).toBeVisible();

    await page.getByRole("button", { name: "+ Nuevo movimiento" }).click();
    const panel = page.getByRole("dialog", { name: "Nuevo movimiento" });
    await panel.getByRole("textbox", { name: /^Nombre/ }).fill(NAME);
    await panel.getByRole("button", { name: "Crear movimiento" }).click();
    await expect(page.getByText(`Movimiento «${NAME}» creado.`)).toBeVisible();

    await page.getByRole("searchbox", { name: "Buscar movimiento" }).fill(NAME);
    const row = page.getByRole("row").filter({ hasText: NAME });
    await expect(row).toBeVisible();
    await expect(row).toContainText("Fuerza");
    expect(await axeViolations(page)).toEqual([]);

    await page.getByRole("button", { name: "+ Nuevo movimiento" }).click();
    const again = page.getByRole("dialog", { name: "Nuevo movimiento" });
    await again.getByRole("textbox", { name: /^Nombre/ }).fill(NAME.toLowerCase());
    await again.getByRole("button", { name: "Crear movimiento" }).click();
    await expect(again.getByText("Ya existe un movimiento con ese nombre.")).toBeVisible();
    await again.getByRole("button", { name: "Cancelar" }).click();

    // Limpieza: el movimiento queda inactivo (no hay DELETE).
    await page.getByRole("button", { name: `Editar ${NAME}` }).click();
    await page.getByRole("dialog", { name: `Editar movimiento · ${NAME}` }).getByRole("checkbox", { name: "Activo" }).uncheck();
    await page.getByRole("dialog", { name: `Editar movimiento · ${NAME}` }).getByRole("button", { name: "Guardar" }).click();
    await expect(page.getByText(`Movimiento «${NAME}» guardado.`)).toBeVisible();
  });

  test("?tab=benchmarks muestra Fran, sembrado por seed-benchmarks", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loginComo(page);
    await page.goto("/movimientos?tab=benchmarks");

    await expect(page.getByRole("heading", { level: 1, name: "Movimientos" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Benchmarks", selected: true })).toBeVisible();
    const fran = page.getByRole("row").filter({ hasText: "Fran" });
    await expect(fran).toBeVisible();
    await expect(fran).toContainText("Tiempo");
    expect(await axeViolations(page)).toEqual([]);
  });
});
