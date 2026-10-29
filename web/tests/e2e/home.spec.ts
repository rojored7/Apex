// S4A-F3 (US-108 a US-110; S4A-D33, S4A-D118) contra `vite preview`: Inicio (Inicio.html) en un
// navegador real con el api simulado por page.route y el reloj fijo en el 20 de octubre de 2026, 2:32
// p. m. de Bogotá. El coach ve los KPI de membresías, ingresos como "Solo administración" (el api le
// manda null), las tarjetas futuras como "Disponible en v0.x" y los últimos movimientos con hora
// relativa; "Por vencer" lleva a /socios?membership_status=expiring; el member va a /mi. axe-core y
// capturas a 320, 768, 1024 y 1440 px en claro y oscuro, sin desborde horizontal. La variante real
// es stack/home.spec.ts.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";
import { json, mockSession } from "./helpers/session";

const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const COACH = { id: "22222222-2222-4222-8222-222222222222", email: "coach@apex.test", role: "coach" } as const;
const MEMBER = { id: "33333333-3333-4333-8333-333333333333", email: "socia@apex.test", role: "member" } as const;
const NOW = new Date("2026-10-20T19:32:00Z");
const LAURA = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const DIEGO = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const WIDTHS = [320, 768, 1024, 1440] as const;

const move = (seq: number, at: string, phrase: string, memberId: string | null = LAURA, table = "members.members") => ({
  seq,
  at,
  table_name: table,
  record_id: memberId,
  member_id: memberId,
  phrase,
});

const COACH_DASHBOARD = {
  today: "2026-10-20",
  members_active: 120,
  members_expiring: 14,
  members_expired: 9,
  members_frozen: 2,
  members_pending_payment: 3,
  income_month: "2026-10",
  income_month_cop: null,
  attendance_week: null,
  sessions_today: null,
  notifications_today: null,
  members_without_consent: null,
  wod_today: null,
  last_movements: [
    move(510, "2026-10-20T19:31:30Z", "admin registró un pago de Laura G.", LAURA, "payments.payments"),
    move(509, "2026-10-20T19:20:00Z", "coach vendió Mensual a Diego M.", DIEGO, "memberships.memberships"),
    move(508, "2026-10-20T17:10:00Z", "admin actualizó los datos de Laura G."),
    move(507, "2026-10-19T22:00:00Z", "admin reactivó a Laura G."),
    move(506, "2026-10-15T15:00:00Z", "admin registró a <b>Laura</b> G."),
  ],
};

async function fakeDashboard(page: Page, body: unknown = COACH_DASHBOARD): Promise<{ calls: () => number }> {
  let calls = 0;
  await page.route("**/api/v1/dashboard", (route: Route) => {
    calls += 1;
    return json(route, 200, body);
  });
  // /socios tras el clic: lista vacía y resumen en cero (la pantalla no es el objeto de esta spec).
  await page.route((url) => url.pathname === "/api/v1/members", (route: Route) => json(route, 200, { items: [], total: 0, limit: 25, offset: 0 }));
  await page.route("**/api/v1/memberships/summary", (route: Route) =>
    json(route, 200, { active: 0, expiring: 0, expired: 0, frozen: 0, pending_payment: 0, expiring_days: 7 }),
  );
  return { calls: () => calls };
}

async function axeViolations(page: Page): Promise<string[]> {
  await page.evaluate(async () => {
    await Promise.all(document.getAnimations().map((animation) => animation.finished.catch(() => undefined)));
  });
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => `${n.target.join(" ")} ${n.failureSummary ?? ""}`).join(", ")}`);
}

const noHorizontalOverflow = (page: Page): Promise<boolean> => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

test.describe("Inicio (preview)", () => {
  test.beforeEach(async ({ page }) => {
    await page.clock.setFixedTime(NOW);
  });

  test("el coach ve KPI, ingresos como Solo administración, futuros y movimientos; Por vencer lleva a /socios", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockSession(page, COACH);
    const api = await fakeDashboard(page);

    await page.goto("/");

    await expect(page.getByRole("heading", { level: 1, name: "Hola, coach · martes 20 de octubre" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Socios al día: 120" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Vencidos: 9" })).toBeVisible();
    await expect(page.getByRole("link", { name: "3 socios con pago pendiente" })).toHaveAttribute("href", "/socios?membership_status=pending_payment");
    const income = page.getByRole("group", { name: "Ingresos de octubre 2026" });
    await expect(income.getByText("Solo administración")).toBeVisible();
    await expect(page.getByText("$ 0")).toHaveCount(0);
    await expect(page.getByRole("group", { name: "Hoy en el box" }).getByText("Disponible en v0.4")).toBeVisible();
    await expect(page.getByRole("group", { name: "Por avisar hoy" }).getByText("Disponible en v0.2")).toBeVisible();

    const movements = page.getByRole("list", { name: "Últimos movimientos" }).getByRole("listitem");
    await expect(movements).toHaveCount(5);
    await expect(movements.nth(0).locator("time")).toHaveText("hace un momento");
    await expect(movements.nth(1).locator("time")).toHaveText("hace 12 min");
    await expect(movements.nth(3).locator("time")).toHaveText("ayer, 5:00 p. m.");
    await expect(movements.nth(1).getByRole("link", { name: "coach vendió Mensual a Diego M." })).toHaveAttribute("href", `/socios/${DIEGO}`);
    await expect(page.getByText("admin registró a <b>Laura</b> G.")).toBeVisible();
    await expect(page.getByRole("link", { name: "Ver auditoría" })).toHaveCount(0);
    expect(api.calls()).toBe(1);

    await page.getByRole("link", { name: "Por vencer: 14" }).click();
    await expect.poll(() => new URL(page.url()).pathname).toBe("/socios");
    expect(new URL(page.url()).searchParams.get("membership_status")).toBe("expiring");
  });

  for (const scheme of ["light", "dark"] as const) {
    for (const width of WIDTHS) {
      test(`Inicio sin violaciones de axe ni desborde en ${scheme} a ${String(width)} px`, async ({ page }, testInfo) => {
        await page.emulateMedia({ colorScheme: scheme });
        await page.setViewportSize({ width, height: 900 });
        await mockSession(page, COACH);
        await fakeDashboard(page);

        await page.goto("/");
        await expect(page.getByRole("link", { name: "Socios al día: 120" })).toBeVisible();
        await expect(page.getByRole("list", { name: "Últimos movimientos" })).toBeVisible();
        expect(await axeViolations(page)).toEqual([]);
        expect(await noHorizontalOverflow(page)).toBe(true);
        await page.screenshot({ path: testInfo.outputPath(`inicio-${scheme}-${String(width)}.png`), fullPage: true });
      });
    }
  }

  test("si el api responde 429, Inicio dice cuánto esperar y Reintentar vuelve a pedir", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockSession(page, COACH);
    let calls = 0;
    await page.route("**/api/v1/dashboard", (route: Route) => {
      calls += 1;
      return calls === 1
        ? route.fulfill({ status: 429, contentType: "application/json", headers: { "Retry-After": "30" }, body: JSON.stringify({ error: { code: "rate_limited", message: "x" } }) })
        : json(route, 200, COACH_DASHBOARD);
    });

    await page.goto("/");

    await expect(page.getByRole("alert")).toContainText("espera 30 segundos");
    await page.getByRole("button", { name: "Reintentar" }).first().click();
    await expect(page.getByRole("link", { name: "Socios al día: 120" })).toBeVisible();
  });

  test("el member que abre / va a /mi sin pedir el tablero", async ({ page }) => {
    await mockSession(page, MEMBER);
    const api = await fakeDashboard(page);

    await page.goto("/");

    await expect.poll(() => new URL(page.url()).pathname).toBe("/mi");
    expect(api.calls()).toBe(0);
  });
});
