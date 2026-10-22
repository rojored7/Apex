// S2-F7 (US-078, US-079) contra el stack de Compose (proyecto `stack`, V4 del plan): el admin crea
// "Trimestral" con un nombre único por corrida y lo ve en la lista con su precio en COP; el mismo
// nombre en minúsculas da 409 bajo "Nombre" (S2-D32). El coach (S2-D26) ve "Sin permiso" en
// /planes y el api solo le entrega planes activos. axe en cada pantalla.
// Necesita B2 a B4 y B9. Sin E2E_BASE_URL se omite: la variante contra `vite preview` es
// ../plans.spec.ts. Idempotente: el nombre lleva la marca de la corrida (V4 corre dos veces).
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { crearCoach, loginComo } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const PLAN_NAME = `Trimestral ${Date.now().toString(36)}`;

interface PlanBody {
  name: string;
  is_active: boolean;
}

async function axeViolations(page: Page): Promise<string[]> {
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

async function fillPlan(page: Page, name: string): Promise<void> {
  const panel = page.getByRole("dialog", { name: "Nuevo plan" });
  await panel.getByRole("textbox", { name: /^Nombre/ }).fill(name);
  await panel.getByRole("textbox", { name: /^Precio \(COP\)/ }).pressSequentially("320000");
  await panel.getByRole("textbox", { name: /^Duración en días/ }).fill("90");
  await panel.getByRole("button", { name: "Crear plan" }).click();
}

test.describe("alta y lista de planes contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con B2 a B4 y B9; en preview corre plans.spec.ts");

  test("el admin crea un plan, lo ve en la lista y el mismo nombre en minúsculas da 409", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loginComo(page);
    await page.goto("/planes");
    await expect(page.getByRole("heading", { level: 1, name: /Planes/ })).toBeVisible();

    await page.getByRole("button", { name: "Nuevo plan" }).click();
    await fillPlan(page, PLAN_NAME);
    await expect(page.getByText(`Plan creado: ${PLAN_NAME}.`)).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);

    await page.getByRole("searchbox", { name: "Buscar" }).fill(PLAN_NAME);
    const link = page.getByRole("link", { name: PLAN_NAME });
    await expect(link).toBeVisible();
    await expect(page.getByRole("row").filter({ has: link })).toContainText("$ 320.000");
    expect(page.url()).not.toContain(encodeURIComponent(PLAN_NAME));

    await page.getByRole("button", { name: "Nuevo plan" }).click();
    await fillPlan(page, PLAN_NAME.toLowerCase());
    const panel = page.getByRole("dialog", { name: "Nuevo plan" });
    await expect(panel.getByText(/Ya existe un plan con este nombre\./)).toBeVisible();
    await expect(panel.getByRole("link", { name: "Ver el plan existente" })).toHaveAttribute("href", /^\/planes\?plan=[0-9a-f-]{36}$/);
    expect(await axeViolations(page)).toEqual([]);
  });

  test("el coach no entra a /planes y el api solo le muestra planes activos", async ({ browser, page }) => {
    const coach = await crearCoach(page);
    const context = await browser.newContext({ baseURL: process.env.E2E_BASE_URL ?? "" });
    const coachPage = await context.newPage();
    await coachPage.setViewportSize({ width: 390, height: 844 });
    const token = await loginComo(coachPage, coach);

    await coachPage.goto("/planes");
    await expect(coachPage.getByRole("heading", { level: 1, name: "Sin permiso" })).toBeVisible();
    expect(await axeViolations(coachPage)).toEqual([]);

    const headers = { Authorization: `Bearer ${token}` };
    const all = await coachPage.request.get("/api/v1/plans", { headers });
    expect(all.status()).toBe(403);
    const active = await coachPage.request.get("/api/v1/plans?active=true&limit=200", { headers });
    expect(active.status()).toBe(200);
    const body = (await active.json()) as { items: PlanBody[] };
    expect(body.items.every((p) => p.is_active)).toBe(true);
    await context.close();
  });
});
