// S4A-F3 (US-108 a US-110; S4A-D33, S4A-D59, L-8) contra el stack de Compose (proyecto `stack`): el
// admin del seed (E2E_ADMIN_*) entra con login real; los KPI de Inicio son los mismos que GET /dashboard
// leído por el api en ese momento, y "Por vencer" lleva a /socios?membership_status=expiring. Sin
// aserciones sobre el orden ni el contenido de los últimos movimientos: el worker y otras specs
// escriben en la auditoría a la vez (S4A-D59). axe y capturas a 320, 768, 1024 y 1440 en claro y
// oscuro. La variante simulada (coach) es ../home.spec.ts.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { THEMES, VIEWPORTS, capture, datosDeBase, esperarTransiciones, exigirStackLocal, loginComo } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];

interface DashboardCounts {
  members_active: number;
  members_expiring: number;
  members_expired: number;
  members_pending_payment: number;
  income_month_cop: number | null;
}

/** "1.250": el separador de miles de formatCount y formatCop. */
const miles = (value: number): string => String(value).replace(/\B(?=(\d{3})+(?!\d))/g, ".");

async function dashboardPorApi(page: Page, token: string): Promise<DashboardCounts> {
  const response = await page.request.get("/api/v1/dashboard", { headers: { Authorization: `Bearer ${token}` } });
  expect(response.status()).toBe(200);
  return (await response.json()) as DashboardCounts;
}

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

test.describe("Inicio contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con B8; en preview corre home.spec.ts");

  test("el admin ve los KPI de GET /dashboard y Por vencer lleva a /socios?membership_status=expiring", async ({ page }) => {
    exigirStackLocal(process.env.E2E_BASE_URL);
    await page.setViewportSize({ width: 1440, height: 900 });
    const token = await loginComo(page, datosDeBase());

    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1, name: /^Hola, / })).toBeVisible();
    await expect(page.getByRole("link", { name: /^Socios al día: / })).toBeVisible();
    // Se lee después de pintar: el api cachea el resumen 30 s, así que los dos ven el mismo corte.
    const api = await dashboardPorApi(page, token);

    await expect(page.getByRole("link", { name: `Socios al día: ${miles(api.members_active)}` })).toBeVisible();
    await expect(page.getByRole("link", { name: `Por vencer: ${miles(api.members_expiring)}` })).toBeVisible();
    await expect(page.getByRole("link", { name: `Vencidos: ${miles(api.members_expired)}` })).toBeVisible();
    expect(api.income_month_cop).not.toBeNull();
    await expect(page.getByRole("link", { name: new RegExp(`^Ingresos de .+: \\$ ${miles(api.income_month_cop ?? 0)}$`) })).toBeVisible();
    await expect(page.getByRole("region", { name: "Últimos movimientos" })).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);

    await page.getByRole("link", { name: `Por vencer: ${miles(api.members_expiring)}` }).click();
    await expect.poll(() => new URL(page.url()).pathname).toBe("/socios");
    expect(new URL(page.url()).searchParams.get("membership_status")).toBe("expiring");
  });

  test("capturas de Inicio a 320, 768, 1024 y 1440 en claro y oscuro, sin violaciones de axe", async ({ page }) => {
    exigirStackLocal(process.env.E2E_BASE_URL);
    await loginComo(page, datosDeBase());
    await page.goto("/");
    await expect(page.getByRole("link", { name: /^Socios al día: / })).toBeVisible();

    for (const theme of THEMES) {
      for (const width of VIEWPORTS) {
        await capture(page, "inicio", theme, width);
        expect(await axeViolations(page)).toEqual([]);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      }
    }
  });
});
