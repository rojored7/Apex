// S3-F4 (US-095) contra `vite preview`: el panel "Registrar pago" abierto por la URL (?pago=) sobre
// una pantalla del panel, en un navegador real con el api simulado por page.route. El panel se
// descarga al pedirlo la URL, registra el saldo con el cuerpo exacto de PaymentIn, pide confirmar un
// pago mayor al saldo (S3-D41) y al cerrarse quita ?pago= de la URL. axe-core en claro y oscuro a
// 390 y 1440 px, sin desborde y con capturas. La variante contra el stack es stack/payment-void.spec.ts.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";
import { mockSession } from "./helpers/session";

const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const COACH_ID = "22222222-2222-4222-8222-222222222222";
const LAURA = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const MEMBERSHIP = "66666666-6666-4666-8666-666666666666";

const ROW = {
  id: MEMBERSHIP,
  member_id: LAURA,
  member_name: "Laura Gómez",
  plan_id: "11111111-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  plan_name: "Mensual",
  status: "pending_payment",
  start_date: "2026-10-25",
  end_date: "2026-11-24",
  agreed_price_cop: 120_000,
  paid_cop: 60_000,
  classes_total: null,
  classes_remaining: null,
};

const json = (route: Route, status: number, body?: unknown) =>
  route.fulfill({ status, contentType: "application/json", body: body === undefined ? "" : JSON.stringify(body) });

async function fakeApi(page: Page): Promise<{ bodies: Record<string, unknown>[] }> {
  const state = { bodies: [] as Record<string, unknown>[] };
  await mockSession(page, { id: COACH_ID, email: "coach@apex.test", role: "coach" });
  await page.route("**/api/v1/payments/methods", (route) =>
    json(route, 200, { items: [{ code: "cash", label: "Efectivo", hint: "" }, { code: "nequi", label: "Nequi", hint: "" }, { code: "breb", label: "Bre-B", hint: "" }] }),
  );
  await page.route(/\/api\/v1\/memberships(\?.*)?$/, (route) => json(route, 200, { items: [ROW], total: 1, limit: 20, offset: 0 }));
  await page.route(`**/api/v1/memberships/${MEMBERSHIP}`, (route) => json(route, 200, { ...ROW, cancel_reason: null, cancelled_at: null, freezes: [], created_at: "2026-10-25T15:00:00Z" }));
  await page.route(`**/api/v1/memberships/${MEMBERSHIP}/payments`, (route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    state.bodies.push(body);
    return json(route, 201, {
      id: "99999999-9999-4999-8999-999999999999",
      membership_id: MEMBERSHIP,
      member_id: LAURA,
      amount_cop: body.amount_cop,
      method: body.method,
      reference: body.reference ?? null,
      paid_at: body.paid_at,
      registered_by: COACH_ID,
      voided: false,
      voided_at: null,
      voided_by: null,
      void_reason: null,
      created_at: "2026-10-25T15:00:00Z",
    });
  });
  return state;
}

async function axeViolations(page: Page): Promise<string[]> {
  await page.evaluate(async () => {
    await Promise.all(document.getAnimations().map((animation) => animation.finished.catch(() => undefined)));
  });
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

test("con ?pago=<membresía> registra el saldo precargado y al cerrar quita ?pago= de la URL", async ({ page }) => {
  const api = await fakeApi(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/?vista=1&pago=${MEMBERSHIP}`);

  const panel = page.getByRole("dialog", { name: "Registrar pago" });
  await expect(panel.getByRole("combobox", { name: /^Membresía/ })).toHaveValue(MEMBERSHIP);
  await expect(panel.getByRole("textbox", { name: /^Valor recibido/ })).toHaveValue("$ 60.000");
  await expect(panel.getByText("Saldo pendiente: $ 60.000")).toBeVisible();
  await panel.getByRole("button", { name: "Registrar" }).click();

  await expect(panel.getByRole("status", { name: "Pago registrado" })).toBeVisible();
  expect(api.bodies).toEqual([expect.objectContaining({ amount_cop: 60_000, method: "cash", confirm_overpayment: false, confirm_duplicate: false })]);
  await panel.getByRole("button", { name: "Listo" }).click();
  await expect(panel).toHaveCount(0);
  await expect(page).toHaveURL(/\/\?vista=1$/);
});

test("un valor mayor al saldo pide confirmación y solo entonces envía confirm_overpayment", async ({ page }) => {
  const api = await fakeApi(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/?pago=${MEMBERSHIP}`);
  const panel = page.getByRole("dialog", { name: "Registrar pago" });
  await expect(panel.getByRole("textbox", { name: /^Valor recibido/ })).toHaveValue("$ 60.000");

  await panel.getByRole("textbox", { name: /^Valor recibido/ }).fill("80000");
  await panel.getByRole("button", { name: "Registrar" }).click();
  const modal = page.getByRole("dialog", { name: "¿Registrar un pago mayor al saldo?" });
  await expect(modal).toContainText("Este pago supera el saldo de la membresía en $ 20.000.");
  expect(api.bodies).toHaveLength(0);
  expect(await axeViolations(page)).toEqual([]);
  await modal.getByRole("button", { name: "Registrar pago" }).click();

  await expect(panel.getByRole("status", { name: "Pago registrado" })).toBeVisible();
  expect(api.bodies).toEqual([expect.objectContaining({ amount_cop: 80_000, confirm_overpayment: true })]);
});

for (const theme of ["light", "dark"] as const) {
  for (const width of [390, 1440]) {
    test(`el panel de pagos con Nequi en ${theme} a ${String(width)} px pasa axe, no desborda y tiene captura`, async ({ page }) => {
      await fakeApi(page);
      await page.emulateMedia({ colorScheme: theme });
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript((value) => {
        try {
          localStorage.setItem("apex.theme", value);
        } catch {
          // Sin almacenamiento el panel queda en claro; la prueba en oscuro lo detectaría.
        }
      }, theme);
      await page.goto(`/?pago=nuevo&socio=${LAURA}`);

      const panel = page.getByRole("dialog", { name: "Registrar pago" });
      await expect(panel.getByRole("combobox", { name: /^Membresía/ })).toHaveValue(MEMBERSHIP);
      await panel.getByText("Nequi", { exact: true }).click();
      await expect(panel.getByRole("textbox", { name: /^Referencia/ })).toBeVisible();
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      expect(await axeViolations(page)).toEqual([]);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(0);
      await page.screenshot({ path: `test-results/captures/pago-panel-${theme}-${String(width)}.png`, fullPage: true });
    });
  }
}
