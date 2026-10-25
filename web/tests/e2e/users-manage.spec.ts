// S2-F4b (US-049 a US-052) contra `vite preview`: gestión de cuentas en un navegador real con
// el api simulado por page.route (con estado: cada acción cambia la fila). Acciones por fila
// (editar, cerrar sesiones, reenviar enlace, bloquear, desbloquear, dar de baja), el panel de
// edición desde `?usuario=<id>` y cerrar las propias sesiones, que termina en /login.
// axe-core sin violaciones a 390 y 1440 px, sin desborde y con capturas. La variante contra el
// stack es stack/users-manage.spec.ts.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";

const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const ADMIN_ID = "11111111-1111-4111-8111-111111111111";
const COACH_ID = "22222222-2222-4222-8222-222222222222";
const LOCKED_ID = "33333333-3333-4333-8333-333333333333";
const RESET_LINK = "http://localhost:4173/restablecer/ReSeTtOkEnAbCdEfGhIjKlMnOpQrStUv0123";

interface FakeRow {
  id: string;
  email: string;
  role: "admin" | "coach" | "member";
  status: "active" | "pending_activation" | "locked" | "inactive" | "deleted";
  member_id: string | null;
  last_login_at: string | null;
  created_at: string;
  active_sessions: number;
}

const initialRows = (): FakeRow[] => [
  { id: ADMIN_ID, email: "admin@apex.test", role: "admin", status: "active", member_id: null, last_login_at: "2026-10-21T19:30:00Z", created_at: "2026-10-01T12:00:00Z", active_sessions: 2 },
  { id: COACH_ID, email: "carlos@apex.test", role: "coach", status: "active", member_id: null, last_login_at: "2026-10-21T13:10:00Z", created_at: "2026-10-20T12:00:00Z", active_sessions: 3 },
  { id: LOCKED_ID, email: "luis@apex.test", role: "coach", status: "locked", member_id: null, last_login_at: "2026-08-12T23:10:00Z", created_at: "2026-08-01T12:00:00Z", active_sessions: 0 },
];

const json = (route: Route, status: number, body?: unknown) =>
  route.fulfill({ status, contentType: "application/json", body: body === undefined ? "" : JSON.stringify(body) });

const userOut = (r: FakeRow) => ({ id: r.id, email: r.email, role: r.role, status: r.status, member_id: r.member_id, must_change_password: false });

interface FakeApi {
  rows: FakeRow[];
  calls: string[];
  patchBodies: unknown[];
}

async function fakeApi(page: Page): Promise<FakeApi> {
  const state: FakeApi = { rows: initialRows(), calls: [], patchBodies: [] };
  let session = true;
  await page.route("**/api/v1/auth/refresh", (route) =>
    session ? json(route, 200, { access_token: "e2e-admin", token_type: "bearer", expires_in: 900 }) : json(route, 401, { error: { code: "invalid_refresh", message: "x" } }),
  );
  await page.route("**/api/v1/auth/me", (route) =>
    json(route, 200, { id: ADMIN_ID, email: "admin@apex.test", role: "admin", member_id: null, gym_name: "Box Norte", must_change_password: false }),
  );
  await page.route(/\/api\/v1\/users(\?.*)?$/, (route) => {
    const url = new URL(route.request().url());
    const visible = state.rows.filter((r) => r.status !== "deleted");
    return json(route, 200, { items: visible, total: visible.length, limit: Number(url.searchParams.get("limit")), offset: Number(url.searchParams.get("offset")) });
  });
  await page.route(/\/api\/v1\/users\/[^/?]+(\/[a-z-]+)?$/, (route) => {
    const request = route.request();
    const [, id = "", action = ""] = /\/users\/([^/?]+)(?:\/([a-z-]+))?$/.exec(new URL(request.url()).pathname) ?? [];
    const row = state.rows.find((r) => r.id === id);
    state.calls.push(`${request.method()} ${action || "user"} ${id}`);
    if (!row) return json(route, 404, { error: { code: "user_not_found", message: "x" } });
    if (request.method() === "GET") return json(route, 200, userOut(row));
    if (request.method() === "PATCH") {
      const body = request.postDataJSON() as Partial<FakeRow>;
      state.patchBodies.push(body);
      Object.assign(row, body);
      return json(route, 200, userOut(row));
    }
    if (request.method() === "DELETE") {
      row.status = "deleted";
      return json(route, 204);
    }
    if (action === "lock") Object.assign(row, { status: "locked", active_sessions: 0 });
    if (action === "unlock") row.status = "active";
    if (action === "revoke-sessions") {
      const revoked = row.active_sessions;
      row.active_sessions = 0;
      if (row.id === ADMIN_ID) session = false;
      return json(route, 200, { revoked });
    }
    if (action === "resend-link") return json(route, 200, { url: RESET_LINK, purpose: "reset", expires_at: "2026-10-21T20:30:00Z" });
    return json(route, 200, userOut(row));
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

const rowOf = (page: Page, email: string) => page.getByRole("row").filter({ has: page.getByRole("link", { name: email, exact: true }) });

for (const [theme, width] of [
  ["light", 1440],
  ["dark", 390],
] as const) {
  test(`acciones de Usuarios en ${theme} a ${String(width)} px pasan axe, no desbordan y tienen captura`, async ({ page }) => {
    await fakeApi(page);
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ colorScheme: theme });
    await page.addInitScript((t) => {
      localStorage.setItem("apex.theme", t);
    }, theme);
    await page.goto("/sistema/usuarios");

    const actions = page.getByRole("group", { name: "Acciones de carlos@apex.test" });
    await expect(actions.getByRole("button", { name: "Cerrar sesiones (3)" })).toBeVisible();
    await expect(page.getByRole("group", { name: "Acciones de admin@apex.test" }).getByRole("button", { name: "Dar de baja" })).toHaveCount(0);
    expect(await axeViolations(page)).toEqual([]);
    await expectNoOverflow(page);
    await page.screenshot({ path: `test-results/captures/usuarios-acciones-${theme}-${String(width)}.png`, fullPage: true });

    await actions.getByRole("button", { name: "Bloquear" }).click();
    await expect(page.getByRole("dialog", { name: "¿Bloquear a carlos@apex.test?" })).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);
    await expectNoOverflow(page);
    await page.screenshot({ path: `test-results/captures/usuarios-bloquear-${theme}-${String(width)}.png`, fullPage: true });
  });
}

test("bloquear, desbloquear, cerrar sesiones y dar de baja cambian la fila y dejan un aviso", async ({ page }) => {
  const api = await fakeApi(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/sistema/usuarios");
  const carlos = page.getByRole("group", { name: "Acciones de carlos@apex.test" });

  await carlos.getByRole("button", { name: "Cerrar sesiones (3)" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Cerrar sesiones" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Se cerraron 3 sesiones de carlos@apex.test." })).toBeVisible();
  await expect(carlos.getByRole("button", { name: "Cerrar sesiones (0)" })).toBeVisible();

  await carlos.getByRole("button", { name: "Bloquear" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Bloquear" }).click();
  await expect(page.getByText("carlos@apex.test quedó bloqueado.")).toBeVisible();
  await expect(rowOf(page, "carlos@apex.test").locator("[data-account=locked]")).toBeVisible();

  await carlos.getByRole("button", { name: "Desbloquear" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Desbloquear" }).click();
  await expect(page.getByText("carlos@apex.test quedó desbloqueado.")).toBeVisible();

  await carlos.getByRole("button", { name: "Dar de baja" }).click();
  const confirm = page.getByRole("dialog", { name: "¿Dar de baja a carlos@apex.test?" });
  await expect(confirm).toContainText("La cuenta pierde el acceso de inmediato. Su historial se conserva.");
  await confirm.getByRole("button", { name: "Dar de baja" }).click();
  await expect(page.getByText("Se dio de baja a carlos@apex.test.")).toBeVisible();
  await expect(page.getByRole("link", { name: "carlos@apex.test", exact: true })).toHaveCount(0);
  expect(api.calls.filter((c) => c.endsWith(COACH_ID) && !c.startsWith("GET"))).toEqual([
    `POST revoke-sessions ${COACH_ID}`,
    `POST lock ${COACH_ID}`,
    `POST unlock ${COACH_ID}`,
    `DELETE user ${COACH_ID}`,
  ]);
});

test("editar desde la fila conserva los filtros y guarda solo lo que cambió", async ({ page }) => {
  const api = await fakeApi(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/sistema/usuarios?role=coach");

  await page.getByRole("group", { name: "Acciones de carlos@apex.test" }).getByRole("link", { name: /^Editar/ }).click();
  const panel = page.getByRole("dialog", { name: "Editar usuario" });
  await expect(panel.getByRole("textbox", { name: /^Correo/ })).toHaveValue("carlos@apex.test");
  expect(new URL(page.url()).search).toBe(`?role=coach&usuario=${COACH_ID}`);
  expect(await axeViolations(page)).toEqual([]);
  await page.screenshot({ path: "test-results/captures/usuarios-editar-light-1440.png", fullPage: true });

  await panel.getByRole("combobox", { name: /^Rol/ }).selectOption("admin");
  await panel.getByRole("button", { name: "Guardar" }).click();

  await expect(page.getByText("Cambios guardados para carlos@apex.test.")).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(new URL(page.url()).search).toBe("?role=coach");
  expect(api.patchBodies).toEqual([{ role: "admin" }]);
});

test("reenviar enlace: se genera, se copia y desaparece al cerrar", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await fakeApi(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/sistema/usuarios");

  await page.getByRole("group", { name: "Acciones de carlos@apex.test" }).getByRole("button", { name: "Reenviar enlace" }).click();
  const modal = page.getByRole("dialog", { name: "Reenviar enlace" });
  await modal.getByRole("button", { name: "Generar enlace" }).click();
  await expect(modal.getByRole("textbox", { name: "Enlace" })).toHaveValue(RESET_LINK);
  await expect(modal).toContainText("Recuperación, vence en 1 hora");
  await modal.getByRole("button", { name: "Copiar" }).click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(RESET_LINK);
  expect(await axeViolations(page)).toEqual([]);
  await expectNoOverflow(page);
  await page.screenshot({ path: "test-results/captures/usuarios-enlace-light-390.png", fullPage: true });

  await modal.getByRole("button", { name: "Listo" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(await page.content()).not.toContain(RESET_LINK);
});

test("cerrar las propias sesiones termina en /login", async ({ page }) => {
  await fakeApi(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/sistema/usuarios");

  await page.getByRole("group", { name: "Acciones de admin@apex.test" }).getByRole("button", { name: "Cerrar sesiones (2)" }).click();
  const confirm = page.getByRole("dialog", { name: "¿Cerrar todas tus sesiones?" });
  await confirm.getByRole("button", { name: "Cerrar sesiones" }).click();

  await expect(page.getByRole("heading", { level: 1, name: "Iniciar sesión" })).toBeVisible();
  expect(new URL(page.url()).pathname).toBe("/login");
});
