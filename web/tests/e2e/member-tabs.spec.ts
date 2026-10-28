// S3-F7 (US-093 y US-101) contra `vite preview`: las pestañas Membresías y Pagos de la ficha en un
// navegador real con el api simulado por page.route. Son rutas hijas de /socios/:id (S3-D65): la ficha
// las pinta en su <Outlet /> sin volver a pedir GET /members/{id}. "Registrar saldo" abre el panel de
// pagos sobre la pestaña (?pago=<membresía>); "Ocultar anulados" viaja como voided=false. axe-core en
// claro y oscuro a 390 y 1440 px, sin desborde y con capturas. La variante contra el stack es
// stack/member-tabs.spec.ts.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";
import { mockSession } from "./helpers/session";

const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const ADMIN = { id: "11111111-1111-4111-8111-111111111111", email: "admin@apex.test", role: "admin" } as const;
const MEMBER_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const CURRENT_ID = "66666666-6666-4666-8666-666666666666";
const FUTURE_ID = "66666666-6666-4666-8666-000000000002";
const PAST_ID = "66666666-6666-4666-8666-000000000003";
const PLAN_ID = "55555555-5555-4555-8555-555555555555";

/** Una fecha civil a `days` días de hoy en Bogotá (UTC-5 todo el año). */
function dayFromToday(days: number): string {
  const bogota = new Date(Date.now() - 5 * 3_600_000);
  bogota.setUTCDate(bogota.getUTCDate() + days);
  return bogota.toISOString().slice(0, 10);
}

const membership = (overrides: Record<string, unknown>) => ({
  id: CURRENT_ID,
  member_id: MEMBER_ID,
  member_name: "Laura Gómez",
  plan_id: PLAN_ID,
  plan_name: "Mensual",
  status: "expiring",
  start_date: dayFromToday(-22),
  end_date: dayFromToday(8),
  agreed_price_cop: 120_000,
  paid_cop: 60_000,
  classes_total: null,
  classes_remaining: null,
  cancel_reason: null,
  cancelled_at: null,
  freezes: [{ id: "f0000000-0000-4000-8000-000000000001", frozen_from: dayFromToday(-15), frozen_to: dayFromToday(-11), days: 5, created_at: "2026-10-01T15:00:00Z" }],
  created_at: "2026-10-01T15:00:00Z",
  ...overrides,
});

const MEMBERSHIPS = [
  membership({ id: FUTURE_ID, plan_name: "Trimestral", status: "pending_payment", start_date: dayFromToday(9), end_date: dayFromToday(99), agreed_price_cop: 320_000, paid_cop: 0, freezes: [] }),
  membership({}),
  membership({ id: PAST_ID, status: "expired", start_date: dayFromToday(-60), end_date: dayFromToday(-30), paid_cop: 120_000, freezes: [] }),
];

const payment = (overrides: Record<string, unknown>) => ({
  id: "99999999-9999-4999-8999-999999999999",
  membership_id: CURRENT_ID,
  member_id: MEMBER_ID,
  member_first_name: "Laura",
  member_last_name: "Gómez",
  plan_name: "Mensual",
  membership_start_date: dayFromToday(-22),
  membership_end_date: dayFromToday(8),
  amount_cop: 60_000,
  method: "nequi",
  reference: "M12345678",
  paid_at: "2026-10-20T19:10:00Z",
  registered_by: ADMIN.id,
  registered_by_name: "a•••@apex.test",
  voided: false,
  void_reason: null,
  backdated: false,
  ...overrides,
});

const PAYMENTS = [
  payment({}),
  payment({ id: "99999999-9999-4999-8999-000000000002", method: "breb", reference: "BRB-99812", paid_at: "2026-10-18T14:00:00Z", voided: true, void_reason: "Duplicado" }),
  payment({ id: "99999999-9999-4999-8999-000000000003", membership_id: PAST_ID, amount_cop: 120_000, method: "cash", reference: null, paid_at: "2026-09-01T15:00:00Z", backdated: true }),
];

const DETAIL = {
  id: MEMBER_ID,
  first_name: "Laura",
  last_name: "Gómez",
  sex: "f",
  status: "active",
  document_type: "CC",
  document: "CC •••• 4417",
  phone: "••• ••• 4567",
  email: "l•••@•••.co",
  birth_date: "••/••/1991",
  emergency_contact: "Registrado",
  data_consent_at: "2026-03-12T15:00:00Z",
  data_consent_version: "2026-03",
  deleted_at: null,
  membership_status: "expiring",
  plan_name: "Mensual",
  membership_end_date: dayFromToday(8),
  created_at: "2026-03-12T15:00:00Z",
  updated_at: "2026-10-20T15:00:00Z",
  warnings: [],
};

const json = (route: Route, status: number, body?: unknown) =>
  route.fulfill({ status, contentType: "application/json", body: body === undefined ? "" : JSON.stringify(body) });

interface FakeApi {
  detailCalls: number;
  paymentQueries: URLSearchParams[];
}

const page25 = (items: unknown[]) => ({ items, total: items.length, limit: 25, offset: 0 });

async function fakeApi(page: Page): Promise<FakeApi> {
  const state: FakeApi = { detailCalls: 0, paymentQueries: [] };
  await mockSession(page, ADMIN);
  await page.route("**/api/v1/payments/methods", (route) =>
    json(route, 200, {
      items: [
        { code: "cash", label: "Efectivo", hint: "" },
        { code: "nequi", label: "Nequi", hint: "" },
        { code: "breb", label: "Bre-B", hint: "" },
      ],
    }),
  );
  await page.route(`**/api/v1/members/${MEMBER_ID}`, (route) => {
    state.detailCalls += 1;
    return json(route, 200, DETAIL);
  });
  await page.route(new RegExp(`/api/v1/members/${MEMBER_ID}/memberships(\\?.*)?$`), (route) => json(route, 200, page25(MEMBERSHIPS)));
  await page.route(new RegExp(`/api/v1/members/${MEMBER_ID}/payments(\\?.*)?$`), (route) => {
    const query = new URL(route.request().url()).searchParams;
    state.paymentQueries.push(query);
    return json(route, 200, page25(query.get("voided") === "false" ? PAYMENTS.filter((p) => !p.voided) : PAYMENTS));
  });
  // El panel de pagos (?pago=<membresía>) lee la membresía y las abiertas del socio.
  await page.route(`**/api/v1/memberships/${CURRENT_ID}`, (route) => json(route, 200, membership({})));
  await page.route(/\/api\/v1\/memberships(\?.*)?$/, (route) => json(route, 200, page25([])));
  return state;
}

async function axeViolations(page: Page): Promise<string[]> {
  await page.evaluate(async () => {
    await Promise.all(document.getAnimations().map((animation) => animation.finished.catch(() => undefined)));
  });
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

async function setTheme(page: Page, theme: "light" | "dark"): Promise<void> {
  await page.emulateMedia({ colorScheme: theme });
  await page.addInitScript((value) => {
    try {
      localStorage.setItem("apex.theme", value);
    } catch {
      // Sin almacenamiento la página queda en claro; la comprobación de data-theme lo detectaría.
    }
  }, theme);
}

test("la pestaña Membresías se abre desde la ficha sin volver a pedirla y Registrar saldo abre el panel con la membresía", async ({ page }) => {
  const api = await fakeApi(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/socios/${MEMBER_ID}`);

  await page.getByRole("tab", { name: "Membresías" }).click();
  await expect(page).toHaveURL(new RegExp(`/socios/${MEMBER_ID}/membresias$`));
  const current = page.getByRole("region", { name: "Membresía vigente" });
  await expect(current).toContainText("Quedan 8 días");
  await expect(page.getByRole("region", { name: "Próxima membresía" })).toContainText("Pendiente de pago");
  expect(api.detailCalls).toBe(1);

  await current.getByRole("link", { name: "Registrar saldo de la membresía Mensual" }).click();
  await expect(page).toHaveURL(new RegExp(`\\?pago=${CURRENT_ID}$`));
  await expect(page.getByRole("dialog", { name: "Registrar pago" })).toBeVisible();
});

test("la pestaña Pagos oculta los anulados con voided=false y lo deja en la URL", async ({ page }) => {
  const api = await fakeApi(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/socios/${MEMBER_ID}/pagos`);

  const table = page.getByRole("region", { name: "Pagos del socio" });
  await expect(table.getByText("Motivo: Duplicado")).toBeVisible();
  // La casilla sigue a la URL: la navegación del router de datos es asíncrona, por eso click y no check.
  await page.getByRole("checkbox", { name: "Ocultar anulados" }).click();
  await expect(page.getByRole("checkbox", { name: "Ocultar anulados" })).toBeChecked();

  await expect(page).toHaveURL(/voided=false/);
  await expect.poll(() => api.paymentQueries.at(-1)?.get("voided") ?? "").toBe("false");
  await expect(table.getByText("Motivo: Duplicado")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Registrar pago" })).toHaveAttribute("href", `/socios/${MEMBER_ID}/pagos?voided=false&pago=nuevo&socio=${MEMBER_ID}`);
});

for (const theme of ["light", "dark"] as const) {
  for (const width of [390, 1440]) {
    test(`las pestañas Membresías y Pagos en ${theme} a ${String(width)} px pasan axe, no desbordan y tienen captura`, async ({ page }) => {
      await fakeApi(page);
      await setTheme(page, theme);
      await page.setViewportSize({ width, height: 900 });

      await page.goto(`/socios/${MEMBER_ID}/membresias`);
      await expect(page.getByRole("region", { name: "Membresía vigente" })).toBeVisible();
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      expect(await axeViolations(page)).toEqual([]);
      const overflow = async () => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(await overflow()).toBeLessThanOrEqual(0);
      await page.screenshot({ path: `test-results/captures/ficha-membresias-${theme}-${String(width)}.png`, fullPage: true });

      await page.getByRole("tab", { name: "Pagos" }).click();
      await expect(page.getByText("Retroactivo").first()).toBeVisible();
      expect(await axeViolations(page)).toEqual([]);
      expect(await overflow()).toBeLessThanOrEqual(0);
      await page.screenshot({ path: `test-results/captures/ficha-pagos-${theme}-${String(width)}.png`, fullPage: true });
    });
  }
}
