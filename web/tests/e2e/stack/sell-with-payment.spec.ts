// S3-F3 (US-084, US-085) contra el stack de Compose (proyecto `stack`, S3-D72): el admin crea por
// el api un socio (documento aleatorio por corrida) y un plan, vende por la pantalla con el pago
// completo, ve "Al día" en la venta registrada y en /socios, y al vender de nuevo recibe el 409
// con "Renovar". axe en cada paso. Al terminar da de baja al socio por el api (baja lógica).
// Necesita B1 a B6 y B9b (estado en la lista): se corre en V4 (E10). Sin E2E_BASE_URL se omite; la
// variante contra `vite preview` es ../sell-with-payment.spec.ts.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { crearPlan, crearSocio, darDeBajaSocio, esperarTransiciones, loginComo, type SocioCreado } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

async function sellFromScreen(page: Page, socio: SocioCreado, planName: string): Promise<void> {
  await page.goto("/membresias/vender");
  await page.getByRole("searchbox", { name: "Buscar socio" }).fill(socio.documento);
  await page.getByRole("button", { name: new RegExp(socio.nombre) }).click();
  await page.getByRole("radio", { name: new RegExp(`^${planName}`) }).check();
  expect(await axeViolations(page)).toEqual([]);
  await page.getByRole("button", { name: "Vender y cobrar" }).click();
}

test.describe("vender con primer pago contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con B1 a B6 y B9b; en preview corre sell-with-payment.spec.ts");

  let socio: SocioCreado | null = null;

  test.afterEach(async ({ page }) => {
    if (socio) await darDeBajaSocio(page, socio.id);
    socio = null;
  });

  test("el admin vende con pago completo, ve Al día y al vender de nuevo recibe el 409 con Renovar", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    socio = await crearSocio(page);
    const plan = await crearPlan(page);
    await loginComo(page);

    await sellFromScreen(page, socio, plan.nombre);
    const done = page.getByRole("region", { name: "Venta registrada" });
    await expect(done).toBeVisible();
    await expect(done.locator("dt", { hasText: "Estado" }).locator("+ dd")).toHaveText("Al día");
    expect(await axeViolations(page)).toEqual([]);

    await page.goto("/socios");
    await page.getByRole("searchbox", { name: "Buscar" }).fill(socio.documento);
    const row = page.getByRole("row", { name: new RegExp(socio.nombre) });
    await expect(row.getByText("Al día")).toBeVisible();
    expect(page.url()).not.toContain(socio.documento);

    await sellFromScreen(page, socio, plan.nombre);
    const alert = page.getByRole("alert");
    await expect(alert).toContainText("ya tiene una membresía vigente o por empezar");
    await expect(alert.getByRole("link", { name: "Renovar" })).toHaveAttribute("href", `/membresias/vender?socio=${socio.id}&renovar=1`);
    expect(await axeViolations(page)).toEqual([]);
  });
});
