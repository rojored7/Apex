// S3-F3 (US-084, US-085, US-088) contra `vite preview`: /membresias/vender en un navegador real con
// el api simulado por page.route. Vender con pago completo (cuerpo exacto de SellMembershipIn y
// "Al día" en la venta registrada), sobrepago con el modal de confirmación (S3-D41) y renovación
// con la vista previa; axe-core en claro y oscuro a 390 y 1440 px, sin desborde y con capturas.
// La variante contra el stack es stack/sell-with-payment.spec.ts (V4, E10).
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";

const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const ADMIN_ID = "11111111-1111-4111-8111-111111111111";
const LAURA = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const MENSUAL = "11111111-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

const MEMBERS = [{ id: LAURA, first_name: "Laura", last_name: "Gómez", sex: "f", status: "active", deleted_at: null, membership_status: null, plan_name: null }];
const PLANS = [
  { id: MENSUAL, name: "Mensual", price_cop: 120_000, kind: "days", duration_days: 30, class_count: null, is_active: true, created_at: "2026-10-20T15:00:00Z", updated_at: "2026-10-20T15:00:00Z" },
  { id: "22222222-bbbb-4bbb-8bbb-bbbbbbbbbbbb", name: "12 clases", price_cop: 110_000, kind: "classes", duration_days: 60, class_count: 12, is_active: true, created_at: "2026-10-20T15:00:00Z", updated_at: "2026-10-20T15:00:00Z" },
];
const METHODS = [
  { code: "cash", label: "Efectivo", hint: "" },
  { code: "nequi", label: "Nequi", hint: "" },
  { code: "breb", label: "Bre-B", hint: "" },
];

const json = (route: Route, status: number, body?: unknown) =>
  route.fulfill({ status, contentType: "application/json", body: body === undefined ? "" : JSON.stringify(body) });

interface FakeApi {
  sellBodies: Record<string, unknown>[];
  previewQueries: string[];
}

function sold(body: Record<string, unknown>): Record<string, unknown> {
  const payment = body.first_payment as { amount_cop?: number } | undefined;
  const paid = payment?.amount_cop ?? 0;
  return {
    id: "66666666-6666-4666-8666-666666666666",
    member_id: LAURA,
    member_name: "Laura Gómez",
    plan_id: MENSUAL,
    plan_name: "Mensual",
    status: paid >= 120_000 ? "active" : "pending_payment",
    start_date: body.renew === true ? "2026-10-29" : String(body.start_date),
    end_date: "2026-11-28",
    agreed_price_cop: 120_000,
    paid_cop: paid,
    classes_total: null,
    classes_remaining: null,
    cancel_reason: null,
    cancelled_at: null,
    freezes: [],
    created_at: "2026-10-28T15:00:00Z",
    first_payment_id: payment ? "77777777-7777-4777-8777-777777777777" : null,
  };
}

async function fakeApi(page: Page): Promise<FakeApi> {
  const state: FakeApi = { sellBodies: [], previewQueries: [] };
  await page.route("**/api/v1/auth/refresh", (route) => json(route, 200, { access_token: "e2e-admin", token_type: "bearer", expires_in: 900 }));
  await page.route("**/api/v1/auth/me", (route) =>
    json(route, 200, { id: ADMIN_ID, email: "admin@apex.test", role: "admin", member_id: null, gym_name: "Box Norte", must_change_password: false }),
  );
  await page.route(/\/api\/v1\/members(\?.*)?$/, (route) => {
    const url = new URL(route.request().url());
    return json(route, 200, { items: MEMBERS, total: MEMBERS.length, limit: Number(url.searchParams.get("limit")), offset: 0 });
  });
  await page.route(/\/api\/v1\/plans(\?.*)?$/, (route) => {
    const url = new URL(route.request().url());
    return json(route, 200, { items: PLANS, total: PLANS.length, limit: Number(url.searchParams.get("limit")), offset: 0 });
  });
  await page.route("**/api/v1/payments/methods", (route) => json(route, 200, { items: METHODS }));
  await page.route(/\/api\/v1\/members\/[^/]+\/memberships\/renewal-preview/, (route) => {
    state.previewQueries.push(new URL(route.request().url()).search);
    return json(route, 200, { start_date: "2026-10-29", end_date: "2026-11-28", agreed_price_cop: 120_000, current_end_date: "2026-10-28" });
  });
  await page.route(/\/api\/v1\/members\/[^/]+\/memberships$/, (route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    state.sellBodies.push(body);
    return json(route, 201, sold(body));
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

async function expectNoOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

async function open(page: Page, path: string, theme: "light" | "dark", width: number): Promise<void> {
  await page.setViewportSize({ width, height: 900 });
  await page.emulateMedia({ colorScheme: theme });
  await page.addInitScript((t) => {
    localStorage.setItem("apex.theme", t);
  }, theme);
  await page.goto(path);
}

async function pickLauraAndMensual(page: Page): Promise<void> {
  await page.getByRole("searchbox", { name: "Buscar socio" }).fill("laura");
  await page.getByRole("button", { name: /Laura Gómez/ }).click();
  await page.getByRole("radio", { name: /^Mensual/ }).check();
}

function summaryValue(page: Page, label: string) {
  return page.getByRole("complementary", { name: "Resumen" }).locator("dt", { hasText: label }).locator("+ dd");
}

for (const [theme, width] of [
  ["light", 1440],
  ["dark", 390],
  ["light", 390],
  ["dark", 1440],
] as const) {
  test(`vender con pago completo en ${theme} a ${String(width)} px: Al día, axe, sin desborde y captura`, async ({ page }) => {
    const api = await fakeApi(page);
    await open(page, "/membresias/vender", theme, width);

    await expect(page.getByRole("heading", { level: 1, name: "Vender membresía" })).toBeVisible();
    await pickLauraAndMensual(page);
    await expect(summaryValue(page, "Pago")).toHaveText("$ 120.000 · Efectivo");
    await expect(summaryValue(page, "Saldo")).toHaveText("$ 0");
    expect(await axeViolations(page)).toEqual([]);
    await expectNoOverflow(page);
    await page.screenshot({ path: `test-results/captures/vender-${theme}-${String(width)}.png`, fullPage: true });

    await page.getByRole("button", { name: "Vender y cobrar" }).click();
    const done = page.getByRole("region", { name: "Venta registrada" });
    await expect(done).toBeVisible();
    await expect(done.locator("dt", { hasText: "Estado" }).locator("+ dd")).toHaveText("Al día");
    expect(api.sellBodies).toHaveLength(1);
    expect(api.sellBodies[0]).toMatchObject({ plan_id: MENSUAL, renew: false, first_payment: { amount_cop: 120_000, method: "cash", confirm_overpayment: false } });
    expect(await axeViolations(page)).toEqual([]);
    await expectNoOverflow(page);
    await page.screenshot({ path: `test-results/captures/vendida-${theme}-${String(width)}.png`, fullPage: true });
  });
}

test("un sobrepago pide confirmación y solo entonces envía confirm_overpayment", async ({ page }) => {
  const api = await fakeApi(page);
  await open(page, "/membresias/vender", "light", 1440);
  await pickLauraAndMensual(page);
  const amount = page.getByRole("textbox", { name: /^Valor recibido/ });
  await amount.fill("150000");
  await page.getByRole("button", { name: "Vender y cobrar" }).click();

  const dialog = page.getByRole("dialog", { name: "¿Registrar un pago mayor al precio?" });
  await expect(dialog).toContainText("Este pago supera el precio del plan en $ 30.000.");
  expect(api.sellBodies).toHaveLength(0);
  expect(await axeViolations(page)).toEqual([]);
  await page.screenshot({ path: "test-results/captures/vender-sobrepago-light-1440.png", fullPage: true });

  await dialog.getByRole("button", { name: "Registrar pago" }).click();
  await expect(page.getByRole("region", { name: "Venta registrada" })).toBeVisible();
  expect(api.sellBodies[0]).toMatchObject({ first_payment: { amount_cop: 150_000, confirm_overpayment: true } });
});

for (const theme of ["light", "dark"] as const) {
  test(`renovar en ${theme}: vista previa, fecha de solo lectura, renew sin start_date y axe`, async ({ page }) => {
    const api = await fakeApi(page);
    await open(page, `/membresias/vender?socio=${LAURA}&renovar=1`, theme, 1440);

    await expect(page.getByRole("heading", { level: 1, name: "Renovar membresía" })).toBeVisible();
    await page.getByRole("radio", { name: /^Mensual/ }).check();
    await expect(page.getByText("Empieza el 29 oct 2026, al día siguiente de que termine la actual.")).toBeVisible();
    await expect(page.getByRole("textbox", { name: "Inicio" })).toHaveAttribute("readonly", "");
    expect(api.previewQueries).toEqual([`?plan_id=${MENSUAL}`]);
    expect(await axeViolations(page)).toEqual([]);
    await page.screenshot({ path: `test-results/captures/renovar-${theme}-1440.png`, fullPage: true });

    await page.getByRole("button", { name: "Vender y cobrar" }).click();
    await expect(page.getByRole("region", { name: "Venta registrada" })).toBeVisible();
    expect(api.sellBodies[0]).toMatchObject({ plan_id: MENSUAL, renew: true });
    expect(api.sellBodies[0]).not.toHaveProperty("start_date");
  });
}

test("la búsqueda del socio nunca llega a la URL y nada queda en el almacenamiento del navegador", async ({ page }) => {
  await fakeApi(page);
  await open(page, "/membresias/vender", "light", 1440);
  await page.getByRole("searchbox", { name: "Buscar socio" }).fill("1020304417");
  await expect(page.getByRole("button", { name: /Laura Gómez/ })).toBeVisible();

  expect(page.url()).not.toContain("1020304417");
  const stored = await page.evaluate(() => {
    const lines: string[] = [];
    for (const storage of [localStorage, sessionStorage]) {
      for (let i = 0; i < storage.length; i += 1) {
        const key = storage.key(i) ?? "";
        lines.push(`${key}=${storage.getItem(key) ?? ""}`);
      }
    }
    return lines.join("\n");
  });
  expect(stored).not.toContain("1020304417");
});
