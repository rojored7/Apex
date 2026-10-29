// S2-F7 (US-078, US-079) contra el stack de Compose (proyecto `stack`, V4 del plan): el admin crea
// "Trimestral" con un nombre único por corrida y lo ve en la lista con su precio en COP; el mismo
// nombre en minúsculas da 409 bajo "Nombre" (S2-D32). El coach (S2-D26) ve "Sin permiso" en
// /planes y el api solo le entrega planes activos. axe en cada pantalla.
// S4A-F4 (US-080, US-081, US-082; S4A-D34): el plan del alta se da de baja al terminar (P2-1) y un
// caso nuevo crea un plan por api, lo edita, lo desactiva y lo da de baja por la pantalla (204), con
// capturas del detalle del plan y de las acciones de la fila. Necesita B7.
// Necesita B2 a B4 y B9. Sin E2E_BASE_URL se omite: la variante contra `vite preview` es
// ../plans.spec.ts. Idempotente: el nombre lleva la marca de la corrida (V4 corre dos veces).
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { borrarUsuario, capture, crearCoach, crearPlan, darDeBajaPlan, esperarTransiciones, exigirStackLocal, loginComo } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const PLAN_NAME = `Trimestral ${Date.now().toString(36)}`;

interface PlanBody {
  name: string;
  is_active: boolean;
}

/** Revisión de F4 (LOW-3): la limpieza que falla en un `finally` queda anotada para V12, sin lanzar. */
function anotarPendiente(aviso: string): void {
  test.info().annotations.push({ type: "plan-pendiente-V12", description: aviso });
}

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
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

    // P2-1: el plan de la corrida no se queda en la base (no tiene ventas: 204). La baja va en el
    // `finally` y no lanza: un fallo de limpieza no tapa el de la prueba (revisión de F4, LOW-3).
    let createdId: string | undefined;
    try {
      await page.getByRole("button", { name: "Nuevo plan" }).click();
      await fillPlan(page, PLAN_NAME);
      await expect(page.getByText(`Plan creado: ${PLAN_NAME}.`)).toBeVisible();
      expect(await axeViolations(page)).toEqual([]);

      await page.getByRole("searchbox", { name: "Buscar" }).fill(PLAN_NAME);
      const link = page.getByRole("link", { name: PLAN_NAME });
      await expect(link).toBeVisible();
      createdId = /plan=([0-9a-f-]{36})/.exec((await link.getAttribute("href")) ?? "")?.[1];
      await expect(page.getByRole("row").filter({ has: link })).toContainText("$ 320.000");
      expect(page.url()).not.toContain(encodeURIComponent(PLAN_NAME));

      await page.getByRole("button", { name: "Nuevo plan" }).click();
      await fillPlan(page, PLAN_NAME.toLowerCase());
      const panel = page.getByRole("dialog", { name: "Nuevo plan" });
      await expect(panel.getByText(/Ya existe un plan con este nombre\./)).toBeVisible();
      await expect(panel.getByRole("link", { name: "Ver el plan existente" })).toHaveAttribute("href", /^\/planes\?plan=[0-9a-f-]{36}$/);
      expect(await axeViolations(page)).toEqual([]);
    } finally {
      if (createdId) await darDeBajaPlan(page, createdId, { tolerante: anotarPendiente });
    }
  });

  test("el admin edita un plan, lo desactiva y lo da de baja desde la fila", async ({ page }) => {
    exigirStackLocal(process.env.E2E_BASE_URL);
    await page.setViewportSize({ width: 1440, height: 900 });
    await loginComo(page);
    const plan = await crearPlan(page, 120_000);
    try {
      await page.goto(`/planes?plan=${plan.id}`);
      const detail = page.getByRole("dialog", { name: plan.nombre });
      await expect(detail.getByText("$ 120.000")).toBeVisible();
      await capture(page, "plan-detalle-stack", "light", 1440);
      await detail.getByRole("button", { name: "Cerrar", exact: true }).click();

      await page.getByRole("searchbox", { name: "Buscar" }).fill(plan.nombre);
      const row = page.getByRole("row").filter({ has: page.getByRole("link", { name: plan.nombre }) });
      await expect(row.getByRole("group", { name: `Acciones de ${plan.nombre}` })).toBeVisible();
      await expect(row).toContainText("Activo");
      await capture(page, "plan-acciones-stack", "light", 1440);
      expect(await axeViolations(page)).toEqual([]);

      await row.getByRole("button", { name: `Editar: ${plan.nombre}` }).click();
      const editor = page.getByRole("dialog", { name: `Editar plan · ${plan.nombre}` });
      await expect(editor.getByText("Cambiar el precio no modifica las membresías ya vendidas.")).toBeVisible();
      const price = editor.getByRole("textbox", { name: /^Precio \(COP\)/ });
      await price.fill("");
      await price.pressSequentially("135000");
      expect(await axeViolations(page)).toEqual([]);
      await editor.getByRole("button", { name: "Guardar" }).click();
      await expect(page.getByText(`Plan guardado: ${plan.nombre}.`)).toBeVisible();
      await expect(row).toContainText("$ 135.000");

      await row.getByRole("button", { name: `Desactivar: ${plan.nombre}` }).click();
      const confirm = page.getByRole("dialog", { name: `¿Desactivar el plan ${plan.nombre}?` });
      await expect(confirm).toContainText("Las membresías vigentes con este plan siguen igual; el plan deja de aparecer al vender.");
      expect(await axeViolations(page)).toEqual([]);
      await confirm.getByRole("button", { name: "Desactivar" }).click();
      await expect(page.getByText(`Plan desactivado: ${plan.nombre}.`)).toBeVisible();
      await expect(row).toContainText("Inactivo");

      const deletion = page.waitForResponse((response) => response.request().method() === "DELETE" && response.url().includes(`/api/v1/plans/${plan.id}`));
      await row.getByRole("button", { name: `Dar de baja: ${plan.nombre}` }).click();
      await page.getByRole("dialog", { name: `¿Dar de baja el plan ${plan.nombre}?` }).getByRole("button", { name: "Dar de baja" }).click();
      expect((await deletion).status()).toBe(204);
      await expect(page.getByText(`Plan dado de baja: ${plan.nombre}.`)).toBeVisible();
      await expect(page.getByRole("link", { name: plan.nombre })).toHaveCount(0);
      expect(await axeViolations(page)).toEqual([]);
    } finally {
      await darDeBajaPlan(page, plan.id, { tolerante: anotarPendiente });
    }
  });

  test("el coach no entra a /planes y el api solo le muestra planes activos", async ({ browser, page }) => {
    const coach = await crearCoach(page);
    const context = await browser.newContext({ baseURL: process.env.E2E_BASE_URL ?? "" });
    try {
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
    } finally {
      await context.close();
      await borrarUsuario(page, coach.id);
    }
  });
});
