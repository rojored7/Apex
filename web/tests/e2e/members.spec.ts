// S2-F6 (US-069, US-070) contra `vite preview`: /socios y /socios/nuevo en un navegador real con
// el api simulado por page.route. Lista (búsqueda fuera de la URL, chip "Dados de baja" en la
// URL), alta (cuerpo de MemberCreate con data_consent, 409 con "Ver socio existente", 201 con
// "Socio registrado"), axe-core en claro y oscuro a 390 y 1440 px, sin desborde y con capturas.
// La variante contra el stack es stack/members.spec.ts.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";
import { mockSession } from "./helpers/session";

const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const ADMIN_ID = "11111111-1111-4111-8111-111111111111";
const EXISTING_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";
const DUPLICATED = "1020304417";

const ROWS = [
  { id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", first_name: "Laura", last_name: "Gómez", sex: "f", status: "active", deleted_at: null, membership_status: null, plan_name: null, membership_end_date: null },
  { id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", first_name: "Andrés", last_name: "Ruiz", sex: "m", status: "inactive", deleted_at: null, membership_status: null, plan_name: null, membership_end_date: null },
  { id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc", first_name: "Elena", last_name: "Vargas", sex: null, status: "active", deleted_at: "2026-10-20T15:00:00Z", membership_status: null, plan_name: null, membership_end_date: null },
];

const json = (route: Route, status: number, body?: unknown) =>
  route.fulfill({ status, contentType: "application/json", body: body === undefined ? "" : JSON.stringify(body) });

interface FakeApi {
  listQueries: string[];
  createBodies: Record<string, unknown>[];
}

async function fakeApi(page: Page): Promise<FakeApi> {
  const state: FakeApi = { listQueries: [], createBodies: [] };
  await mockSession(page, { id: ADMIN_ID, email: "admin@apex.test", role: "admin" });
  await page.route(/\/api\/v1\/members(\?.*)?$/, (route) => {
    const request = route.request();
    if (request.method() === "POST") {
      const body = request.postDataJSON() as Record<string, unknown>;
      state.createBodies.push(body);
      if (body.document === DUPLICATED) {
        return json(route, 409, { error: { code: "member_document_duplicated", message: "Ya existe un socio con este documento", field: "document", existing_id: EXISTING_ID } });
      }
      return json(route, 201, {
        id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        first_name: body.first_name,
        last_name: body.last_name,
        sex: null,
        status: "active",
        document_type: "CC",
        document: "CC •••• 9988",
        phone: null,
        email: null,
        birth_date: null,
        emergency_contact: null,
        data_consent_at: body.data_consent ? "2026-10-22T15:00:00Z" : null,
        data_consent_version: body.data_consent ? "2026-10" : null,
        deleted_at: null,
        membership_status: null,
        plan_name: null,
        membership_end_date: null,
        created_at: "2026-10-22T15:00:00Z",
        updated_at: "2026-10-22T15:00:00Z",
        warnings: body.data_consent ? [] : ["data_consent_missing"],
      });
    }
    const url = new URL(request.url());
    state.listQueries.push(url.search);
    const q = url.searchParams.get("q")?.toLowerCase();
    const items = q ? ROWS.filter((r) => `${r.first_name} ${r.last_name}`.toLowerCase().includes(q)) : ROWS;
    return json(route, 200, { items, total: items.length, limit: Number(url.searchParams.get("limit")), offset: Number(url.searchParams.get("offset")) });
  });
  return state;
}

/** Todo lo guardado en localStorage y sessionStorage, como texto. */
function storedText(): string {
  const lines: string[] = [];
  for (const storage of [localStorage, sessionStorage]) {
    for (let i = 0; i < storage.length; i += 1) {
      const key = storage.key(i) ?? "";
      lines.push(`${key}=${storage.getItem(key) ?? ""}`);
    }
  }
  return lines.join("\n");
}

async function axeViolations(page: Page): Promise<string[]> {
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
  test(`Socios en ${theme} a ${String(width)} px pasa axe, no desborda y tiene captura`, async ({ page }) => {
    await fakeApi(page);
    await open(page, "/socios", theme, width);

    await expect(page.getByText("3 en total")).toBeVisible();
    await expect(page.locator("[data-account=deleted]")).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);
    await expectNoOverflow(page);
    await page.screenshot({ path: `test-results/captures/socios-${theme}-${String(width)}.png`, fullPage: true });
  });

  test(`Nuevo socio en ${theme} a ${String(width)} px pasa axe, no desborda y tiene captura`, async ({ page }) => {
    await fakeApi(page);
    await open(page, "/socios/nuevo", theme, width);

    await expect(page.getByRole("heading", { level: 1, name: "Nuevo socio" })).toBeVisible();
    await page.getByRole("button", { name: "Guardar" }).click();
    await expect(page.getByText("Escribe el nombre del socio.")).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);
    await expectNoOverflow(page);
    await page.screenshot({ path: `test-results/captures/socio-nuevo-${theme}-${String(width)}.png`, fullPage: true });
  });
}

test("la búsqueda va al api y nunca a la URL; el chip de dados de baja sí", async ({ page }) => {
  const api = await fakeApi(page);
  await open(page, "/socios", "light", 1440);
  await expect(page.getByRole("link", { name: "Andrés Ruiz" })).toBeVisible();

  await page.getByRole("searchbox", { name: "Buscar" }).fill("laura");
  await expect(page.getByRole("link", { name: "Andrés Ruiz" })).toHaveCount(0);
  await expect.poll(() => api.listQueries.some((s) => s.includes("q=laura"))).toBe(true);
  await expect(page.getByRole("link", { name: "Laura Gómez" })).toBeVisible();
  expect(page.url()).not.toContain("laura");

  await page.getByRole("group", { name: "Estado" }).getByRole("button", { name: "Dados de baja" }).click();
  await expect.poll(() => new URL(page.url()).search).toBe("?status=deleted");
  expect(page.url()).not.toContain("laura");
});

test("alta: el 409 enlaza al socio existente y el 201 vuelve a la lista con el aviso", async ({ page }) => {
  const api = await fakeApi(page);
  await open(page, "/socios", "light", 1440);

  await page.getByRole("link", { name: "Nuevo socio" }).click();
  await expect(page).toHaveURL(/\/socios\/nuevo$/);
  await page.getByRole("textbox", { name: /^Nombres/ }).fill("Sara");
  await page.getByRole("textbox", { name: /^Apellidos/ }).fill("Mejía");
  await page.getByRole("textbox", { name: /^Número de documento/ }).fill(DUPLICATED);
  await page.getByRole("button", { name: "Guardar" }).click();

  const existing = page.getByRole("link", { name: "Ver socio existente" });
  await expect(existing).toHaveAttribute("href", `/socios/${EXISTING_ID}`);
  expect(await axeViolations(page)).toEqual([]);
  await page.screenshot({ path: "test-results/captures/socio-duplicado-light-1440.png", fullPage: true });

  await page.getByRole("textbox", { name: /^Número de documento/ }).fill("5566779988");
  await page.getByRole("checkbox", { name: "El socio autorizó el tratamiento de datos" }).check();
  await page.getByRole("button", { name: "Guardar" }).click();

  await expect(page).toHaveURL(/\/socios$/);
  await expect(page.getByText("Socio registrado: Sara Mejía.")).toBeVisible();
  expect(api.createBodies.at(-1)).toEqual({ first_name: "Sara", last_name: "Mejía", document_type: "CC", document: "5566779988", data_consent: true });
  expect(Object.keys(api.createBodies.at(-1) ?? {})).not.toContain("data_consent_at");
  expect(await page.evaluate(storedText)).not.toContain("5566779988");
});
