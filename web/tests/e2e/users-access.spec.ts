// S2-F4a (US-045 a US-048) contra `vite preview`: las pantallas nuevas en un navegador real
// con el api simulado por page.route. Usuarios (lista, búsqueda fuera de la URL, alta con el
// enlace y su descarte), restablecer (el token sale de la barra, 204 lleva a /login con
// aviso), recuperar (mensaje fijo) y "Mi cuenta". axe-core en claro y oscuro, sin desborde a
// 390 y 1440 px y con capturas. La variante contra el stack es stack/users-activation.spec.ts.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";

const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const TOKEN = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789-_";
const LINK = `http://localhost:4173/restablecer/${TOKEN}`;
const PASSWORD = "Clave-nueva-segura-2026";

const ROWS = [
  { id: "11111111-1111-4111-8111-111111111111", email: "admin@apex.test", role: "admin", status: "active", member_id: null, last_login_at: "2026-10-21T19:30:00Z", created_at: "2026-10-01T12:00:00Z", active_sessions: 1 },
  { id: "22222222-2222-4222-8222-222222222222", email: "carlos@apex.test", role: "coach", status: "pending_activation", member_id: null, last_login_at: null, created_at: "2026-10-20T12:00:00Z", active_sessions: 0 },
  { id: "33333333-3333-4333-8333-333333333333", email: "luis@apex.test", role: "coach", status: "locked", member_id: null, last_login_at: "2026-08-12T23:10:00Z", created_at: "2026-08-01T12:00:00Z", active_sessions: 0 },
];

const json = (route: Route, status: number, body?: unknown) =>
  route.fulfill({ status, contentType: "application/json", body: body === undefined ? "" : JSON.stringify(body) });

interface FakeApi {
  listQueries: string[];
  passwordBodies: unknown[];
  resetBodies: unknown[];
}

async function fakeApi(page: Page, { session = true }: { session?: boolean } = {}): Promise<FakeApi> {
  const state: FakeApi = { listQueries: [], passwordBodies: [], resetBodies: [] };
  await page.route("**/api/v1/auth/refresh", (route) =>
    session ? json(route, 200, { access_token: "e2e-admin", token_type: "bearer", expires_in: 900 }) : json(route, 401, { error: { code: "invalid_refresh", message: "x" } }),
  );
  await page.route("**/api/v1/auth/me", (route) =>
    json(route, 200, { id: ROWS[0]?.id, email: "admin@apex.test", role: "admin", member_id: null, gym_name: "Box Norte", must_change_password: false }),
  );
  await page.route("**/api/v1/auth/me/password", (route) => {
    state.passwordBodies.push(route.request().postDataJSON());
    return json(route, 200, { access_token: "e2e-admin-2", token_type: "bearer", expires_in: 900 });
  });
  await page.route("**/api/v1/auth/reset", (route) => {
    state.resetBodies.push(route.request().postDataJSON());
    return json(route, 204);
  });
  await page.route("**/api/v1/auth/forgot", (route) => json(route, 204));
  await page.route(/\/api\/v1\/users(\?.*)?$/, (route) => {
    const url = new URL(route.request().url());
    if (route.request().method() === "POST") {
      return json(route, 201, {
        user: { id: "55555555-5555-4555-8555-555555555555", email: "nuevo@apex.test", role: "coach", status: "pending_activation", member_id: null, must_change_password: false },
        activation_url: LINK,
        expires_at: "2026-10-25T19:30:00Z",
      });
    }
    state.listQueries.push(url.search);
    const q = url.searchParams.get("q");
    const items = q ? ROWS.filter((r) => r.email.includes(q)) : ROWS;
    return json(route, 200, { items, total: items.length, limit: Number(url.searchParams.get("limit")), offset: Number(url.searchParams.get("offset")) });
  });
  return state;
}

async function axeViolations(page: Page): Promise<string[]> {
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

async function expectNoOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

for (const [theme, width] of [
  ["light", 1440],
  ["dark", 390],
] as const) {
  test(`Usuarios en ${theme} a ${String(width)} px pasa axe, no desborda y tiene captura`, async ({ page }) => {
    await fakeApi(page);
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ colorScheme: theme });
    await page.addInitScript((t) => {
      localStorage.setItem("apex.theme", t);
    }, theme);
    await page.goto("/sistema/usuarios");

    await expect(page.getByText("3 en total")).toBeVisible();
    await expect(page.locator("[data-account=pending_activation]")).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);
    await expectNoOverflow(page);
    await page.screenshot({ path: `test-results/captures/usuarios-${theme}-${String(width)}.png`, fullPage: true });
  });
}

test("la búsqueda va al api y nunca a la URL; los filtros sí", async ({ page }) => {
  const api = await fakeApi(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/sistema/usuarios");
  await expect(page.getByRole("link", { name: "luis@apex.test", exact: true })).toBeVisible();

  await page.getByRole("searchbox", { name: "Buscar" }).fill("luis");
  await expect(page.getByRole("link", { name: "admin@apex.test", exact: true })).toHaveCount(0);
  await expect.poll(() => api.listQueries.some((s) => s.includes("q=luis"))).toBe(true);
  await expect(page.getByRole("link", { name: "luis@apex.test", exact: true })).toBeVisible();
  expect(page.url()).not.toContain("luis");

  await page.getByRole("combobox", { name: "Rol" }).selectOption("coach");
  await expect.poll(() => new URL(page.url()).search).toBe("?role=coach");
});

test("alta: el enlace se muestra, se copia y desaparece al cerrar", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await fakeApi(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/sistema/usuarios");

  await page.getByRole("button", { name: "Nuevo usuario del equipo" }).click();
  const panel = page.getByRole("dialog", { name: "Nuevo usuario del equipo" });
  await panel.getByRole("textbox", { name: /^Correo/ }).fill("nuevo@apex.test");
  await panel.getByRole("button", { name: "Crear usuario" }).click();
  await expect(panel.getByRole("textbox", { name: "Enlace de activación" })).toHaveValue(LINK);
  await panel.getByRole("button", { name: "Copiar" }).click();
  await expect(panel.getByText("Enlace copiado.")).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(LINK);
  expect(await axeViolations(page)).toEqual([]);
  await page.screenshot({ path: "test-results/captures/usuarios-alta-light-1440.png", fullPage: true });

  await panel.getByRole("button", { name: "Listo" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(await page.content()).not.toContain(TOKEN);
});

test("restablecer: el token sale de la barra y el 204 lleva a /login con el aviso", async ({ page }) => {
  const api = await fakeApi(page, { session: false });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/restablecer/${TOKEN}`);

  await expect(page.getByRole("heading", { level: 1, name: "Nueva contraseña" })).toBeVisible();
  await expect.poll(() => new URL(page.url()).pathname).toBe("/restablecer");
  expect(page.url()).not.toContain(TOKEN);
  expect(await axeViolations(page)).toEqual([]);
  await expectNoOverflow(page);
  await page.screenshot({ path: "test-results/captures/restablecer-light-390.png", fullPage: true });

  await page.getByLabel(/^Contraseña nueva/).fill(PASSWORD);
  await page.getByLabel(/^Repite la contraseña nueva/).fill(PASSWORD);
  await page.getByRole("button", { name: "Guardar contraseña" }).click();

  await expect(page.getByRole("heading", { level: 1, name: "Iniciar sesión" })).toBeVisible();
  await expect(page.getByText("Tu contraseña quedó guardada. Inicia sesión con ella.")).toBeVisible();
  expect(api.resetBodies).toEqual([{ token: TOKEN, new_password: PASSWORD }]);
});

test("recuperar: siempre el mismo mensaje", async ({ page }) => {
  await fakeApi(page, { session: false });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/recuperar");

  await page.getByRole("textbox", { name: "Correo" }).fill("quien@apex.test");
  await page.getByRole("button", { name: "Enviar enlace" }).click();

  await expect(page.getByRole("status")).toHaveText("Pídele al administrador tu enlace de recuperación.");
  expect(await axeViolations(page)).toEqual([]);
  await expectNoOverflow(page);
});

test("Mi cuenta: cambia la contraseña, cierra el panel y avisa", async ({ page }) => {
  const api = await fakeApi(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");

  await page.getByRole("button", { name: /admin@apex\.test/ }).click();
  await page.getByRole("menuitem", { name: "Mi cuenta" }).click();
  const panel = page.getByRole("dialog", { name: "Mi cuenta" });
  await expect(panel.getByText("Box Norte")).toBeVisible();
  expect(await axeViolations(page)).toEqual([]);

  await panel.getByLabel(/^Contraseña actual/).fill("Clave-inicial-2026");
  await panel.getByLabel(/^Contraseña nueva/).fill(PASSWORD);
  await panel.getByLabel(/^Repite la contraseña nueva/).fill(PASSWORD);
  await panel.getByRole("button", { name: "Cambiar contraseña" }).click();

  await expect(page.getByRole("status").filter({ hasText: "Contraseña actualizada" })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(api.passwordBodies).toEqual([{ current_password: "Clave-inicial-2026", new_password: PASSWORD }]);
  expect(await axeViolations(page)).toEqual([]);
});
