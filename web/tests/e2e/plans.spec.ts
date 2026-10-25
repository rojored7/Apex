// S2-F7 (US-078, US-079) contra `vite preview`: /planes en un navegador real con el api simulado
// por page.route. Lista (búsqueda fuera de la URL, el filtro de estado en la URL), alta con el precio en
// formato "$ 120.000" (409 bajo "Nombre" y 201 con "Plan creado"), detalle de solo lectura y
// axe-core en claro y oscuro a 390 y 1440 px, sin desborde y con capturas. La variante contra el
// stack es stack/plans.spec.ts.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";

const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const ADMIN_ID = "11111111-1111-4111-8111-111111111111";
const DUPLICATED_ID = "22222222-bbbb-4bbb-8bbb-bbbbbbbbbbbb";

const plan = (id: string, name: string, extra: Record<string, unknown> = {}) => ({
  id,
  name,
  price_cop: 120_000,
  kind: "days",
  duration_days: 30,
  class_count: null,
  is_active: true,
  created_at: "2026-10-20T15:00:00Z",
  updated_at: "2026-10-20T15:00:00Z",
  ...extra,
});

const ROWS = [
  plan("11111111-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "12 clases", { price_cop: 110_000, kind: "classes", duration_days: 60, class_count: 12 }),
  plan(DUPLICATED_ID, "Mensual"),
  plan("33333333-cccc-4ccc-8ccc-cccccccccccc", "Promo apertura", { price_cop: 90_000, is_active: false }),
];

const json = (route: Route, status: number, body?: unknown) =>
  route.fulfill({ status, contentType: "application/json", body: body === undefined ? "" : JSON.stringify(body) });

interface FakeApi {
  listQueries: string[];
  createBodies: Record<string, unknown>[];
}

async function fakeApi(page: Page): Promise<FakeApi> {
  const state: FakeApi = { listQueries: [], createBodies: [] };
  const created: ReturnType<typeof plan>[] = [];
  await page.route("**/api/v1/auth/refresh", (route) => json(route, 200, { access_token: "e2e-admin", token_type: "bearer", expires_in: 900 }));
  await page.route("**/api/v1/auth/me", (route) =>
    json(route, 200, { id: ADMIN_ID, email: "admin@apex.test", role: "admin", member_id: null, gym_name: "Box Norte", must_change_password: false }),
  );
  await page.route(/\/api\/v1\/plans\/[0-9a-f-]+$/, (route) => {
    const id = new URL(route.request().url()).pathname.split("/").at(-1);
    const found = [...ROWS, ...created].find((r) => r.id === id);
    return found ? json(route, 200, found) : json(route, 404, { error: { code: "plan_not_found", message: "No se encontró el plan." } });
  });
  await page.route(/\/api\/v1\/plans(\?.*)?$/, (route) => {
    const request = route.request();
    if (request.method() === "POST") {
      const body = request.postDataJSON() as Record<string, unknown>;
      state.createBodies.push(body);
      if (String(body.name).toLowerCase() === "mensual") {
        return json(route, 409, { error: { code: "plan_name_duplicated", message: "Ya existe un plan con este nombre", field: "name", existing_id: DUPLICATED_ID } });
      }
      const row = plan("44444444-dddd-4ddd-8ddd-dddddddddddd", String(body.name), { ...body, class_count: body.class_count ?? null });
      created.push(row);
      return json(route, 201, row);
    }
    const url = new URL(request.url());
    state.listQueries.push(url.search);
    const q = url.searchParams.get("q")?.toLowerCase();
    const active = url.searchParams.get("active");
    const items = [...ROWS, ...created].filter((r) => (!q || r.name.toLowerCase().includes(q)) && (active === null || String(r.is_active) === active));
    return json(route, 200, { items, total: items.length, limit: Number(url.searchParams.get("limit")), offset: Number(url.searchParams.get("offset")) });
  });
  return state;
}

async function axeViolations(page: Page): Promise<string[]> {
  // V4 del Sprint 3: el hover de un botón recién pulsado pasa por colores intermedios; se mide al final.
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

for (const [theme, width] of [
  ["light", 1440],
  ["dark", 390],
  ["light", 390],
  ["dark", 1440],
] as const) {
  test(`Planes en ${theme} a ${String(width)} px pasa axe, no desborda y tiene captura`, async ({ page }) => {
    await fakeApi(page);
    await open(page, "/planes", theme, width);

    await expect(page.getByText("3 en total")).toBeVisible();
    await expect(page.getByText("$ 110.000").first()).toBeVisible();
    await expect(page.locator("[data-account=inactive]")).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);
    await expectNoOverflow(page);
    await page.screenshot({ path: `test-results/captures/planes-${theme}-${String(width)}.png`, fullPage: true });
  });

  test(`Nuevo plan en ${theme} a ${String(width)} px pasa axe, no desborda y tiene captura`, async ({ page }) => {
    await fakeApi(page);
    await open(page, "/planes", theme, width);

    await page.getByRole("button", { name: "Nuevo plan" }).click();
    const panel = page.getByRole("dialog", { name: "Nuevo plan" });
    await panel.getByRole("combobox", { name: /^Tipo de duración/ }).selectOption({ label: "Por número de clases" });
    await panel.getByRole("button", { name: "Crear plan" }).click();
    await expect(panel.getByText("Escribe el nombre del plan.")).toBeVisible();
    await expect(panel.getByText("Escribe cuántas clases incluye el plan.")).toBeVisible();
    // El puntero sigue sobre "Crear plan": axe mide el hover ya terminado (la transición dura
    // 120 ms). En oscuro el texto sigue negro (DESIGN.md, Temas); en claro pasa a blanco.
    const create = panel.getByRole("button", { name: "Crear plan" });
    await expect(create).toHaveCSS("background-color", theme === "dark" ? "rgb(51, 181, 234)" : "rgb(0, 119, 173)");
    await expect(create).toHaveCSS("color", theme === "dark" ? "rgb(14, 14, 14)" : "rgb(255, 255, 255)");
    expect(await axeViolations(page)).toEqual([]);
    await expectNoOverflow(page);
    await page.screenshot({ path: `test-results/captures/plan-nuevo-${theme}-${String(width)}.png`, fullPage: true });
  });

  test(`Detalle del plan en ${theme} a ${String(width)} px pasa axe y tiene captura`, async ({ page }) => {
    await fakeApi(page);
    await open(page, `/planes?plan=${DUPLICATED_ID}`, theme, width);

    const panel = page.getByRole("dialog", { name: "Mensual" });
    await expect(panel.getByText("$ 120.000")).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);
    await expectNoOverflow(page);
    await page.screenshot({ path: `test-results/captures/plan-detalle-${theme}-${String(width)}.png`, fullPage: true });
  });
}

test("la búsqueda va al api y nunca a la URL; el filtro de estado sí", async ({ page }) => {
  const api = await fakeApi(page);
  await open(page, "/planes", "light", 1440);
  await expect(page.getByRole("link", { name: "Promo apertura" })).toBeVisible();

  await page.getByRole("searchbox", { name: "Buscar" }).fill("mens");
  await expect(page.getByRole("link", { name: "Promo apertura" })).toHaveCount(0);
  await expect.poll(() => api.listQueries.some((s) => s.includes("q=mens"))).toBe(true);
  await expect(page.getByRole("link", { name: "Mensual" })).toBeVisible();
  expect(page.url()).not.toContain("mens");

  await page.getByRole("searchbox", { name: "Buscar" }).fill("");
  await page.getByRole("combobox", { name: "Estado" }).selectOption({ label: "Inactivos" });
  await expect.poll(() => new URL(page.url()).search).toBe("?active=false");
  await expect(page.getByRole("link", { name: "Promo apertura" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Mensual" })).toHaveCount(0);
});

test("alta: el precio se escribe con formato, el 409 va bajo Nombre y el 201 avisa Plan creado", async ({ page }) => {
  const api = await fakeApi(page);
  await open(page, "/planes", "light", 1440);

  await page.getByRole("button", { name: "Nuevo plan" }).click();
  const panel = page.getByRole("dialog", { name: "Nuevo plan" });
  await panel.getByRole("textbox", { name: /^Nombre/ }).fill("mensual");
  await panel.getByRole("textbox", { name: /^Precio \(COP\)/ }).pressSequentially("320000");
  await expect(panel.getByRole("textbox", { name: /^Precio \(COP\)/ })).toHaveValue("$ 320.000");
  await panel.getByRole("textbox", { name: /^Duración en días/ }).fill("90");
  await panel.getByRole("button", { name: "Crear plan" }).click();

  await expect(panel.getByText(/Ya existe un plan con este nombre\./)).toBeVisible();
  await expect(panel.getByRole("link", { name: "Ver el plan existente" })).toHaveAttribute("href", `/planes?plan=${DUPLICATED_ID}`);
  // axe mide el hover de "Crear plan" ya terminado (transición de 120 ms).
  await expect(panel.getByRole("button", { name: "Crear plan" })).toHaveCSS("color", "rgb(255, 255, 255)");
  expect(await axeViolations(page)).toEqual([]);
  await page.screenshot({ path: "test-results/captures/plan-duplicado-light-1440.png", fullPage: true });

  await panel.getByRole("textbox", { name: /^Nombre/ }).fill("Trimestral");
  await panel.getByRole("button", { name: "Crear plan" }).click();

  await expect(page.getByText("Plan creado: Trimestral.")).toBeVisible();
  await expect(page.getByRole("dialog", { name: "Nuevo plan" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Trimestral" })).toBeVisible();
  expect(api.createBodies.at(-1)).toEqual({ name: "Trimestral", price_cop: 320_000, kind: "days", duration_days: 90 });
});
