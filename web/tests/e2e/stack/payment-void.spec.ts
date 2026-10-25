// S3-F4 (US-095, US-097; S3-D72) contra el stack de Compose (proyecto `stack`). El admin crea por el
// api un socio (documento aleatorio por corrida) y un plan de 120.000, le vende la membresía con un
// pago parcial de 60.000, registra el saldo por el panel (?pago=<membresía>, sin modal), intenta un
// tercer pago mayor al saldo (modal de Q5 y confirmación), anula ese tercero con motivo desde
// /pagos, ve "Anulado" y comprueba que un segundo "Anular" desde otra pestaña da el 409 ("Otra
// persona lo anuló antes"). axe en cada paso; al terminar da de baja al socio (baja lógica).
// La anulación se hace desde la pantalla de pagos (S3-F6): los selectores siguen Pagos.html ("Ver",
// "Detalle del pago", "Anular pago") y F6 los ajusta si su pantalla cambia. Se corre en V4 (F4.6:
// sin Docker desde el worktree); sin E2E_BASE_URL se omite.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { crearPlan, crearSocio, darDeBajaSocio, esperarTransiciones, loginComo, venderMembresia, type SocioCreado } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const REASON = "Pago registrado por error en la prueba";

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

async function registerFromPanel(page: Page): Promise<string> {
  const panel = page.getByRole("dialog", { name: "Registrar pago" });
  const response = page.waitForResponse((r) => r.request().method() === "POST" && /\/api\/v1\/memberships\/[^/]+\/payments$/.test(new URL(r.url()).pathname));
  await panel.getByRole("button", { name: "Registrar" }).click();
  return response.then(async (r) => {
    expect(r.status()).toBe(201);
    return ((await r.json()) as { id: string }).id;
  });
}

async function openPaymentDetail(page: Page, socio: SocioCreado, amount: string): Promise<void> {
  await page.goto("/pagos");
  await page.getByRole("searchbox", { name: "Buscar" }).fill(socio.documento);
  const row = page.getByRole("row", { name: new RegExp(`${socio.nombre}.*${amount.replace(/[$.]/g, "\\$&")}`) }).first();
  await row.getByRole("button", { name: "Ver" }).click();
  await expect(page.getByRole("dialog", { name: /Detalle del pago/ })).toBeVisible();
}

test.describe("registrar y anular pagos contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con B3 a B8 y la pantalla de pagos (S3-F6); se corre en V4");

  let socio: SocioCreado | null = null;

  test.afterEach(async ({ page }) => {
    if (socio) await darDeBajaSocio(page, socio.id);
    socio = null;
  });

  test("abono, saldo por el panel, tercer pago confirmado, anulación con motivo y 409 al repetirla", async ({ page, context }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    socio = await crearSocio(page);
    const plan = await crearPlan(page);
    const membership = await venderMembresia(page, socio.id, plan.id, { amount_cop: 60_000, method: "cash" });
    expect(membership.status).toBe("pending_payment");
    await loginComo(page);

    // 1. El saldo de 60.000 por el panel: precargado y sin modal.
    await page.goto(`/socios?pago=${membership.id}`);
    const panel = page.getByRole("dialog", { name: "Registrar pago" });
    await expect(panel.getByRole("textbox", { name: /^Valor recibido/ })).toHaveValue("$ 60.000");
    expect(await axeViolations(page)).toEqual([]);
    await registerFromPanel(page);
    await expect(panel.getByRole("status", { name: "Pago registrado" })).toBeVisible();
    await expect(page.getByRole("dialog", { name: "¿Registrar un pago mayor al saldo?" })).toHaveCount(0);

    // 2. Un tercer pago con la membresía ya cubierta: modal de Q5 y confirmación.
    await panel.getByRole("button", { name: "Registrar otro pago" }).click();
    await panel.getByRole("textbox", { name: /^Valor recibido/ }).fill("10000");
    await panel.getByRole("button", { name: "Registrar" }).click();
    const overpay = page.getByRole("dialog", { name: "¿Registrar un pago mayor al saldo?" });
    await expect(overpay).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);
    const third = page.waitForResponse((r) => r.request().method() === "POST" && /\/payments$/.test(new URL(r.url()).pathname) && r.status() === 201);
    await overpay.getByRole("button", { name: "Registrar pago" }).click();
    const thirdResponse = await third;
    expect((thirdResponse.request().postDataJSON() as { confirm_overpayment: boolean }).confirm_overpayment).toBe(true);
    await expect(panel.getByRole("status", { name: "Pago registrado" })).toBeVisible();
    await panel.getByRole("button", { name: "Cerrar" }).first().click();
    await expect(page).not.toHaveURL(/pago=/);

    // 3. Otra pestaña abre el mismo pago antes de anularlo (para el 409 del paso 5).
    const stale = await context.newPage();
    await stale.setViewportSize({ width: 1440, height: 900 });
    await openPaymentDetail(stale, socio, "$ 10.000");

    // 4. Anular el tercero con motivo: queda "Anulado".
    await openPaymentDetail(page, socio, "$ 10.000");
    await page.getByRole("dialog", { name: /Detalle del pago/ }).getByRole("button", { name: "Anular pago" }).click();
    const voidModal = page.getByRole("dialog", { name: "¿Anular este pago?" });
    await expect(voidModal).toContainText("El pago no se borra: queda anulado con este motivo.");
    await voidModal.getByRole("textbox", { name: /^Motivo/ }).fill(REASON);
    expect(await axeViolations(page)).toEqual([]);
    await voidModal.getByRole("button", { name: "Anular pago" }).click();
    await expect(page.getByRole("dialog", { name: "Pago anulado" })).toBeVisible();
    await page.getByRole("dialog", { name: "Pago anulado" }).getByRole("button", { name: "Cerrar" }).click();
    await expect(page.getByRole("row", { name: new RegExp(socio.nombre) }).filter({ hasText: "Anulado" })).toHaveCount(1);

    // 5. El segundo "Anular" (desde la pestaña vieja) da el 409.
    await stale.getByRole("dialog", { name: /Detalle del pago/ }).getByRole("button", { name: "Anular pago" }).click();
    const staleModal = stale.getByRole("dialog", { name: "¿Anular este pago?" });
    await staleModal.getByRole("textbox", { name: /^Motivo/ }).fill(REASON);
    await staleModal.getByRole("button", { name: "Anular pago" }).click();
    await expect(staleModal.getByRole("alert")).toContainText("Otra persona lo anuló antes");
    expect(await axeViolations(stale)).toEqual([]);
    await stale.close();
  });
});
