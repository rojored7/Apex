// S3-F5 (US-089 a US-092) contra `vite preview`: la lista /membresias en un navegador real con el api
// simulado por page.route. El coach congela 10 días por el modal (vista previa "Son 10 días…" y el
// cuerpo exacto de FreezeIn) y el admin anula con motivo (cuerpo { reason }); los dos ven el aviso de
// la página. axe-core en claro y oscuro a 390 y 1440 px (lista y modales), sin desborde y con
// capturas. La variante contra el stack es stack/memberships-freeze-cancel.spec.ts.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";

const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const USERS = {
  coach: { id: "22222222-2222-4222-8222-222222222222", email: "coach@apex.test", role: "coach" },
  admin: { id: "11111111-1111-4111-8111-111111111111", email: "admin@apex.test", role: "admin" },
} as const;
const ELENA = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const ELENA_MEMBERSHIP = "99999999-aaaa-4999-8999-999999999999";
const MENSUAL = "11111111-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

const row = (overrides: Record<string, unknown>) => ({
  id: "66666666-6666-4666-8666-666666666666",
  member_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  member_name: "Laura Gómez",
  plan_id: MENSUAL,
  plan_name: "Mensual",
  status: "pending_payment",
  start_date: "2026-10-25",
  end_date: "2026-11-24",
  agreed_price_cop: 120_000,
  paid_cop: 60_000,
  classes_total: null,
  classes_remaining: null,
  ...overrides,
});

const ROWS = [
  row({}),
  row({
    id: "77777777-7777-4777-8777-777777777777",
    member_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    member_name: "Andrés Ruiz",
    plan_id: "22222222-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    plan_name: "12 clases",
    status: "expiring",
    start_date: "2026-09-01",
    end_date: "2026-10-31",
    agreed_price_cop: 110_000,
    paid_cop: 110_000,
    classes_total: 12,
    classes_remaining: 2,
  }),
  row({ id: ELENA_MEMBERSHIP, member_id: ELENA, member_name: "Elena Vargas", status: "active", start_date: "2026-10-01", end_date: "2026-10-31", paid_cop: 120_000 }),
];

const json = (route: Route, status: number, body?: unknown) =>
  route.fulfill({ status, contentType: "application/json", body: body === undefined ? "" : JSON.stringify(body) });

const membershipOut = (overrides: Record<string, unknown>) => ({
  ...row({ id: ELENA_MEMBERSHIP, member_id: ELENA, member_name: "Elena Vargas", status: "active", start_date: "2026-10-01", end_date: "2026-10-31", paid_cop: 120_000 }),
  cancel_reason: null,
  cancelled_at: null,
  freezes: [],
  created_at: "2026-10-01T15:00:00Z",
  ...overrides,
});

interface FakeApi {
  freezeBodies: unknown[];
  cancelBodies: unknown[];
}

async function fakeApi(page: Page, who: keyof typeof USERS): Promise<FakeApi> {
  const state: FakeApi = { freezeBodies: [], cancelBodies: [] };
  const user = USERS[who];
  await page.route("**/api/v1/auth/refresh", (route) => json(route, 200, { access_token: `e2e-${who}`, token_type: "bearer", expires_in: 900 }));
  await page.route("**/api/v1/auth/me", (route) => json(route, 200, { ...user, member_id: null, gym_name: "Box Norte", must_change_password: false }));
  await page.route(/\/api\/v1\/plans(\?.*)?$/, (route) =>
    json(route, 200, {
      items: [
        { id: "22222222-bbbb-4bbb-8bbb-bbbbbbbbbbbb", name: "12 clases", price_cop: 110_000, kind: "classes", duration_days: 60, class_count: 12, is_active: true, created_at: "2026-10-20T15:00:00Z", updated_at: "2026-10-20T15:00:00Z" },
        { id: MENSUAL, name: "Mensual", price_cop: 120_000, kind: "days", duration_days: 30, class_count: null, is_active: true, created_at: "2026-10-20T15:00:00Z", updated_at: "2026-10-20T15:00:00Z" },
      ],
      total: 2,
      limit: 100,
      offset: 0,
    }),
  );
  await page.route("**/api/v1/memberships/summary", (route) => json(route, 200, { active: 210, expiring: 18, expired: 12, frozen: 3, pending_payment: 5 }));
  await page.route(/\/api\/v1\/memberships(\?.*)?$/, (route) => json(route, 200, { items: ROWS, total: ROWS.length, limit: 25, offset: 0 }));
  await page.route(`**/api/v1/memberships/${ELENA_MEMBERSHIP}/freeze`, (route) => {
    state.freezeBodies.push(route.request().postDataJSON());
    return json(route, 200, membershipOut({ status: "frozen", end_date: "2026-11-10" }));
  });
  await page.route(`**/api/v1/memberships/${ELENA_MEMBERSHIP}/cancel`, (route) => {
    state.cancelBodies.push(route.request().postDataJSON());
    return json(route, 200, membershipOut({ status: "cancelled", cancel_reason: "Vendida por error", cancelled_at: "2026-10-28T15:00:00Z" }));
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

test("el coach congela 10 días por el modal y ve el nuevo fin", async ({ page }) => {
  const api = await fakeApi(page, "coach");
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/membresias");

  await expect(page.getByRole("heading", { level: 1, name: /^Membresías/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Anular/ })).toHaveCount(0);
  await page.getByRole("button", { name: "Congelar la membresía de Elena Vargas" }).click();
  const modal = page.getByRole("dialog", { name: "Congelar la membresía de Elena Vargas" });
  await modal.getByLabel(/^Desde/).fill("2026-10-28");
  await modal.getByLabel(/^Hasta/).fill("2026-11-06");
  await expect(modal.getByText("Son 10 días; la membresía terminará el 10 nov 2026")).toBeVisible();
  await modal.getByRole("button", { name: "Congelar" }).click();

  await expect(modal).toHaveCount(0);
  await expect(page.getByText("Membresía de Elena Vargas congelada. Ahora termina el 10 nov 2026.")).toBeVisible();
  expect(api.freezeBodies).toEqual([{ frozen_from: "2026-10-28", frozen_to: "2026-11-06" }]);
});

test("el admin anula con motivo y ve el aviso", async ({ page }) => {
  const api = await fakeApi(page, "admin");
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/membresias");

  await page.getByRole("button", { name: "Anular la membresía de Elena Vargas" }).click();
  const modal = page.getByRole("dialog", { name: "¿Anular la membresía de Elena Vargas?" });
  await expect(modal).toContainText("Los pagos asociados no se tocan: si hay que devolver dinero, se anula el pago aparte.");
  await modal.getByRole("textbox", { name: /^Motivo/ }).fill("Vendida por error");
  await modal.getByRole("button", { name: "Sí, anular" }).click();

  await expect(modal).toHaveCount(0);
  await expect(page.getByText("Membresía de Elena Vargas anulada. Sus pagos siguen registrados.")).toBeVisible();
  expect(api.cancelBodies).toEqual([{ reason: "Vendida por error" }]);
});

test("los filtros quedan en la URL: status separado por comas", async ({ page }) => {
  await fakeApi(page, "coach");
  await page.setViewportSize({ width: 1440, height: 900 });
  const requests: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname === "/api/v1/memberships") requests.push(url.search);
  });
  await page.goto("/membresias");

  const chips = page.getByRole("group", { name: "Estado" });
  await chips.getByRole("button", { name: /^Por vencer/ }).click();
  await chips.getByRole("button", { name: /^Pendiente de pago/ }).click();

  await expect(page).toHaveURL(/\?status=expiring%2Cpending_payment$/);
  await expect.poll(() => requests.at(-1) ?? "").toContain("status=expiring%2Cpending_payment");
});

for (const theme of ["light", "dark"] as const) {
  for (const width of [390, 1440]) {
    test(`la lista y los dos modales en ${theme} a ${String(width)} px pasan axe, no desbordan y tienen captura`, async ({ page }) => {
      await fakeApi(page, "admin");
      await setTheme(page, theme);
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/membresias");

      await expect(page.getByRole("link", { name: "Elena Vargas", exact: true })).toBeVisible();
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      expect(await axeViolations(page)).toEqual([]);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(0);
      await page.screenshot({ path: `test-results/captures/membresias-${theme}-${String(width)}.png`, fullPage: true });

      await page.getByRole("button", { name: "Congelar la membresía de Elena Vargas" }).click();
      const freeze = page.getByRole("dialog", { name: "Congelar la membresía de Elena Vargas" });
      await freeze.getByLabel(/^Desde/).fill("2026-10-28");
      await freeze.getByLabel(/^Hasta/).fill("2026-11-06");
      await expect(freeze.getByText("Son 10 días; la membresía terminará el 10 nov 2026")).toBeVisible();
      expect(await axeViolations(page)).toEqual([]);
      await page.screenshot({ path: `test-results/captures/membresias-congelar-${theme}-${String(width)}.png` });
      await freeze.getByRole("button", { name: "Volver" }).click();

      await page.getByRole("button", { name: "Anular la membresía de Elena Vargas" }).click();
      const cancel = page.getByRole("dialog", { name: "¿Anular la membresía de Elena Vargas?" });
      await cancel.getByRole("textbox", { name: /^Motivo/ }).fill("Vendida por error");
      const confirm = cancel.getByRole("button", { name: "Sí, anular" });
      await expect(confirm).toBeEnabled();
      // El botón tiene una transición de 120 ms al habilitarse: axe la vería a medias.
      await expect(confirm).toHaveCSS("opacity", "1");
      expect(await axeViolations(page)).toEqual([]);
      await cancel.getByRole("button", { name: "Volver" }).click();
    });
  }
}
