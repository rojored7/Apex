// S3-F2 (US-071, US-072; S3-D72) contra `vite preview`: /socios en el celular (Socios_Movil.html)
// con el api simulado por page.route y 60 socios. A 390 × 844 y 320 × 640, en claro y oscuro: la
// lista son tarjetas, "Cargar más" acumula dos veces hasta los 60 y desaparece, la página no se
// desplaza de lado (scrollWidth <= innerWidth), axe sin violaciones y capturas. Buscar "laura"
// (sin llegar a la URL) y abrir su ficha (la ficha llega con S3-F1: aquí solo se comprueba la
// navegación a /socios/:id). Un chip deja `membership_status` en la URL y en la petición.
// La variante contra el stack es stack/members-mobile.spec.ts.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";

const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const ADMIN_ID = "11111111-1111-4111-8111-111111111111";
const TOTAL = 60;

interface Row {
  id: string;
  first_name: string;
  last_name: string;
  sex: "f" | "m" | null;
  status: "active" | "inactive";
  deleted_at: string | null;
  membership_status: string | null;
  plan_name: string | null;
  membership_end_date: string | null;
}

const STATES = ["active", "expiring", "expired", "frozen", "pending_payment", "none"] as const;

const ROWS: Row[] = Array.from({ length: TOTAL }, (_, index) => {
  const n = String(index + 1).padStart(2, "0");
  const state = STATES[index % STATES.length] ?? "none";
  const hasPlan = state !== "none";
  return {
    id: `${String(index + 1).padStart(8, "0")}-0000-4000-8000-000000000000`,
    first_name: index === 0 ? "Laura" : `Socio ${n}`,
    last_name: index === 0 ? "Gómez" : "Prueba",
    sex: index % 2 === 0 ? "f" : "m",
    status: index % 7 === 3 ? "inactive" : "active",
    deleted_at: null,
    membership_status: state,
    plan_name: hasPlan ? (index % 2 === 0 ? "Mensual" : "12 clases") : null,
    membership_end_date: hasPlan ? "2026-11-27" : null,
  };
});
const LAURA = ROWS[0] as Row;

const json = (route: Route, status: number, body?: unknown) =>
  route.fulfill({ status, contentType: "application/json", body: body === undefined ? "" : JSON.stringify(body) });

interface FakeApi {
  listQueries: string[];
}

async function fakeApi(page: Page): Promise<FakeApi> {
  const state: FakeApi = { listQueries: [] };
  await page.route("**/api/v1/auth/refresh", (route) => json(route, 200, { access_token: "e2e-admin", token_type: "bearer", expires_in: 900 }));
  await page.route("**/api/v1/auth/me", (route) =>
    json(route, 200, { id: ADMIN_ID, email: "admin@apex.test", role: "admin", member_id: null, gym_name: "Box Norte", must_change_password: false }),
  );
  await page.route("**/api/v1/memberships/summary", (route) => json(route, 200, { active: 10, expiring: 10, expired: 10, frozen: 10, pending_payment: 10 }));
  await page.route(/\/api\/v1\/plans(\?.*)?$/, (route) =>
    json(route, 200, {
      items: [
        { id: "22222222-bbbb-4bbb-8bbb-bbbbbbbbbbbb", name: "12 clases", price_cop: 110000, kind: "classes", duration_days: 60, class_count: 12, is_active: true, created_at: "2026-10-20T15:00:00Z", updated_at: "2026-10-20T15:00:00Z" },
        { id: "11111111-aaaa-4aaa-8aaa-aaaaaaaaaaaa", name: "Mensual", price_cop: 120000, kind: "days", duration_days: 30, class_count: null, is_active: true, created_at: "2026-10-20T15:00:00Z", updated_at: "2026-10-20T15:00:00Z" },
      ],
      total: 2,
      limit: 200,
      offset: 0,
    }),
  );
  await page.route(/\/api\/v1\/members(\?.*)?$/, (route) => {
    const url = new URL(route.request().url());
    state.listQueries.push(url.search);
    const q = url.searchParams.get("q")?.toLowerCase();
    const membership = url.searchParams.get("membership_status");
    const matches = ROWS.filter((r) => (!q || `${r.first_name} ${r.last_name}`.toLowerCase().includes(q)) && (!membership || r.membership_status === membership));
    const limit = Number(url.searchParams.get("limit"));
    const offset = Number(url.searchParams.get("offset"));
    return json(route, 200, { items: matches.slice(offset, offset + limit), total: matches.length, limit, offset });
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

async function expectNoSideScroll(page: Page): Promise<void> {
  const sizes = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, inner: window.innerWidth }));
  expect(sizes.scroll).toBeLessThanOrEqual(sizes.inner);
}

async function open(page: Page, path: string, theme: "light" | "dark", width: number, height: number): Promise<void> {
  await page.setViewportSize({ width, height });
  await page.emulateMedia({ colorScheme: theme });
  await page.addInitScript((t) => {
    localStorage.setItem("apex.theme", t);
  }, theme);
  await page.goto(path);
}

const cards = (page: Page) => page.getByRole("list", { name: "Socios" }).getByRole("listitem");

for (const [width, height] of [
  [390, 844],
  [320, 640],
] as const) {
  for (const theme of ["light", "dark"] as const) {
    test(`Socios en el celular a ${String(width)}×${String(height)} en ${theme}: tarjetas, Cargar más dos veces, sin desborde y axe`, async ({ page }) => {
      const api = await fakeApi(page);
      await open(page, "/socios", theme, width, height);

      await expect(cards(page)).toHaveCount(25);
      await expect(page.getByRole("table")).toHaveCount(0);
      await expect(page.getByRole("link", { name: "Nuevo socio" })).toBeVisible();
      expect(await axeViolations(page)).toEqual([]);
      await expectNoSideScroll(page);
      await page.screenshot({ path: `test-results/captures/socios-movil-${theme}-${String(width)}.png`, fullPage: true });

      await page.getByRole("button", { name: "Cargar más" }).click();
      await expect(cards(page)).toHaveCount(50);
      await page.getByRole("button", { name: "Cargar más" }).click();
      await expect(cards(page)).toHaveCount(60);
      await expect(page.getByRole("button", { name: "Cargar más" })).toHaveCount(0);
      await expect(page.getByText(`Mostrando ${String(TOTAL)} de ${String(TOTAL)}`)).toBeVisible();

      for (const offset of [0, 25, 50]) expect(api.listQueries.filter((s) => s === `?limit=25&offset=${String(offset)}`)).toHaveLength(1);
      expect(await axeViolations(page)).toEqual([]);
      await expectNoSideScroll(page);
      await page.screenshot({ path: `test-results/captures/socios-movil-todos-${theme}-${String(width)}.png`, fullPage: true });
    });
  }

  test(`a ${String(width)}×${String(height)} buscar "laura" no llega a la URL y su tarjeta abre la ficha`, async ({ page }) => {
    const api = await fakeApi(page);
    await open(page, "/socios", "light", width, height);
    await expect(cards(page)).toHaveCount(25);

    await page.getByRole("searchbox", { name: "Buscar" }).fill("laura");
    await expect(cards(page)).toHaveCount(1);
    await expect.poll(() => api.listQueries.some((s) => s.includes("q=laura"))).toBe(true);
    expect(page.url()).not.toContain("laura");

    await page.getByRole("link", { name: "Laura Gómez" }).click();
    await expect(page).toHaveURL(new RegExp(`/socios/${LAURA.id}$`));
  });

  test(`a ${String(width)}×${String(height)} un chip filtra por membresía en la URL y en la petición`, async ({ page }) => {
    const api = await fakeApi(page);
    await open(page, "/socios", "light", width, height);
    await expect(cards(page)).toHaveCount(25);

    await page.getByRole("group", { name: "Estado" }).getByRole("button", { name: /^Vencidos/ }).click();

    await expect.poll(() => new URL(page.url()).search).toBe("?membership_status=expired");
    await expect(cards(page)).toHaveCount(10);
    await expect.poll(() => api.listQueries.includes("?limit=25&offset=0&membership_status=expired")).toBe(true);
    await expectNoSideScroll(page);
  });
}
