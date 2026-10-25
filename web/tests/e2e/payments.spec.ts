// S3-F6 (US-098 a US-100) contra `vite preview`: la pantalla /pagos en un navegador real con el api
// simulado por page.route. El rango de fechas queda en la URL como días y viaja al api en UTC con
// `to` exclusivo; el estado arranca en Todos (D37); el resumen del mes sigue `?mes=`. El admin abre el
// detalle de un pago y lo anula con motivo (cuerpo { reason }). axe-core en claro y oscuro a 390 y
// 1440 px (lista y detalle), sin desborde y con capturas. La variante contra el stack es
// stack/payment-void.spec.ts.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";

const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const USERS = {
  coach: { id: "22222222-2222-4222-8222-222222222222", email: "coach@apex.test", role: "coach" },
  admin: { id: "11111111-1111-4111-8111-111111111111", email: "admin@apex.test", role: "admin" },
} as const;
const LAURA_PAYMENT = "99999999-9999-4999-8999-999999999999";

const row = (overrides: Record<string, unknown>) => ({
  id: LAURA_PAYMENT,
  membership_id: "66666666-6666-4666-8666-666666666666",
  member_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  member_first_name: "Laura",
  member_last_name: "Gómez",
  plan_name: "Mensual",
  membership_start_date: "2026-10-29",
  membership_end_date: "2026-11-28",
  amount_cop: 120_000,
  method: "nequi",
  reference: "M12345678",
  paid_at: "2026-10-20T19:10:00Z",
  registered_by: USERS.coach.id,
  registered_by_name: "c•••@apex.test",
  voided: false,
  void_reason: null,
  backdated: false,
  ...overrides,
});

const ROWS = [
  row({}),
  row({
    id: "99999999-9999-4999-8999-000000000002",
    member_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
    member_first_name: "Diego",
    member_last_name: "Mora",
    method: "cash",
    reference: null,
    paid_at: "2026-10-20T16:52:00Z",
    registered_by: USERS.admin.id,
    registered_by_name: "a•••@apex.test",
  }),
  row({
    id: "99999999-9999-4999-8999-000000000003",
    member_id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
    member_first_name: "Sofía",
    member_last_name: "Pardo",
    amount_cop: 60_000,
    method: "breb",
    reference: "BRB-99812",
    paid_at: "2026-10-19T23:28:00Z",
    voided: true,
    void_reason: "Duplicado",
    backdated: true,
  }),
];

const json = (route: Route, status: number, body?: unknown) =>
  route.fulfill({ status, contentType: "application/json", body: body === undefined ? "" : JSON.stringify(body) });

interface FakeApi {
  listQueries: URLSearchParams[];
  summaryMonths: string[];
  voidBodies: unknown[];
}

async function fakeApi(page: Page, who: keyof typeof USERS): Promise<FakeApi> {
  const state: FakeApi = { listQueries: [], summaryMonths: [], voidBodies: [] };
  const user = USERS[who];
  await page.route("**/api/v1/auth/refresh", (route) => json(route, 200, { access_token: `e2e-${who}`, token_type: "bearer", expires_in: 900 }));
  await page.route("**/api/v1/auth/me", (route) => json(route, 200, { ...user, member_id: null, gym_name: "Box Norte", must_change_password: false }));
  await page.route("**/api/v1/payments/methods", (route) =>
    json(route, 200, {
      items: [
        { code: "cash", label: "Efectivo", hint: "" },
        { code: "nequi", label: "Nequi", hint: "" },
        { code: "breb", label: "Bre-B", hint: "" },
      ],
    }),
  );
  await page.route(/\/api\/v1\/payments\/summary(\?.*)?$/, (route) => {
    const month = new URL(route.request().url()).searchParams.get("month") ?? "";
    state.summaryMonths.push(month);
    return json(route, 200, { month, total_cop: 18_240_000, payments_count: 152, voided_count: 3, by_method: { cash: 9_100_000, nequi: 6_340_000, breb: 2_800_000 } });
  });
  await page.route(/\/api\/v1\/payments(\?.*)?$/, (route) => {
    state.listQueries.push(new URL(route.request().url()).searchParams);
    return json(route, 200, { items: ROWS, total: ROWS.length, limit: 25, offset: 0 });
  });
  await page.route(`**/api/v1/payments/${LAURA_PAYMENT}`, (route) =>
    json(route, 200, { ...row({}), voided_by: null, voided_by_name: null, voided_at: null, created_at: "2026-10-20T19:10:00Z" }),
  );
  await page.route(`**/api/v1/payments/${LAURA_PAYMENT}/void`, (route) => {
    state.voidBodies.push(route.request().postDataJSON());
    return json(route, 200, {
      id: LAURA_PAYMENT,
      membership_id: "66666666-6666-4666-8666-666666666666",
      member_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      amount_cop: 120_000,
      method: "nequi",
      reference: "M12345678",
      paid_at: "2026-10-20T19:10:00Z",
      registered_by: USERS.coach.id,
      voided: true,
      voided_at: "2026-10-28T15:00:00Z",
      voided_by: USERS.admin.id,
      void_reason: "Pago duplicado",
      created_at: "2026-10-20T19:10:00Z",
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

test("los filtros quedan en la URL como días y viajan en UTC con 'to' exclusivo; el estado arranca en Todos", async ({ page }) => {
  const api = await fakeApi(page, "coach");
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/pagos");

  await expect(page.getByRole("heading", { level: 1, name: /^Pagos/ })).toBeVisible();
  const filters = page.getByRole("search");
  await expect(filters.getByRole("combobox", { name: "Estado" })).toHaveValue("");
  await filters.getByLabel("Desde").fill("2026-10-01");
  await filters.getByLabel("Hasta").fill("2026-10-20");
  await filters.getByRole("combobox", { name: "Medio" }).selectOption("nequi");

  await expect(page).toHaveURL(/\?from=2026-10-01&to=2026-10-20&method=nequi$/);
  await expect.poll(() => api.listQueries.at(-1)?.get("method") ?? "").toBe("nequi");
  const last = api.listQueries.at(-1);
  expect(last?.get("from")).toBe("2026-10-01T05:00:00.000Z");
  expect(last?.get("to")).toBe("2026-10-21T05:00:00.000Z");
  expect(last?.has("voided")).toBe(false);
  await expect(page.getByRole("button", { name: /^Anular/ })).toHaveCount(0);
});

test("el resumen del mes sigue ?mes= y la búsqueda no llega a la URL", async ({ page }) => {
  const api = await fakeApi(page, "coach");
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/pagos?mes=2026-09");

  const summary = page.getByRole("region", { name: "Resumen del mes" });
  await expect(summary.getByRole("group", { name: "Septiembre 2026 · total" })).toContainText("$ 18.240.000");
  expect(api.summaryMonths).toContain("2026-09");

  await page.getByRole("searchbox", { name: "Buscar" }).fill("M12345678");
  await expect.poll(() => api.listQueries.at(-1)?.get("q") ?? "").toBe("M12345678");
  expect(page.url()).not.toContain("M12345678");
});

test("el admin abre el detalle y anula el pago con motivo", async ({ page }) => {
  const api = await fakeApi(page, "admin");
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/pagos");

  await page.getByRole("button", { name: "Ver el pago de Laura Gómez" }).click();
  const detail = page.getByRole("dialog", { name: "Detalle del pago" });
  await expect(detail).toContainText("c•••@apex.test");
  await detail.getByRole("button", { name: "Anular pago" }).click();
  const confirm = page.getByRole("dialog", { name: "¿Anular este pago?" });
  await confirm.getByRole("textbox", { name: /^Motivo/ }).fill("Pago duplicado");
  await confirm.getByRole("button", { name: "Anular pago" }).click();

  await expect(page.getByRole("dialog", { name: "Pago anulado" })).toBeVisible();
  expect(api.voidBodies).toEqual([{ reason: "Pago duplicado" }]);
});

for (const theme of ["light", "dark"] as const) {
  for (const width of [390, 1440]) {
    test(`la lista y el detalle en ${theme} a ${String(width)} px pasan axe, no desbordan y tienen captura`, async ({ page }) => {
      await fakeApi(page, "admin");
      await setTheme(page, theme);
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/pagos");

      await expect(page.getByRole("link", { name: "Sofía Pardo", exact: true })).toBeVisible();
      await expect(page.getByText("Retroactivo").first()).toBeVisible();
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      expect(await axeViolations(page)).toEqual([]);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(0);
      await page.screenshot({ path: `test-results/captures/pagos-${theme}-${String(width)}.png`, fullPage: true });

      await page.getByRole("button", { name: "Ver el pago de Laura Gómez" }).click();
      const detail = page.getByRole("dialog", { name: "Detalle del pago" });
      await expect(detail.getByRole("link", { name: "Laura Gómez" })).toBeVisible();
      expect(await axeViolations(page)).toEqual([]);
      await page.screenshot({ path: `test-results/captures/pagos-detalle-${theme}-${String(width)}.png` });
      await detail.getByRole("button", { name: "Cerrar" }).click();
      await expect(detail).toHaveCount(0);
    });
  }
}
