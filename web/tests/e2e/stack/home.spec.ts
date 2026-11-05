// S4A-F3 (US-108 a US-110; S4A-D33, S4A-D59, L-8) contra el stack de Compose (proyecto `stack`): el
// admin del seed (E2E_ADMIN_*) entra con login real; los KPI de Inicio son los mismos que GET /dashboard
// leído por el api en ese momento, y "Por vencer" lleva a /socios?membership_status=expiring. Sin
// aserciones sobre el orden ni el contenido de los últimos movimientos: el worker y otras specs
// escriben en la auditoría a la vez (S4A-D59). axe y capturas a 320, 768, 1024 y 1440 en claro y
// oscuro. La variante simulada (coach) es ../home.spec.ts.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { THEMES, VIEWPORTS, capture, datosDeBase, esperarTransiciones, exigirStackLocal, loginComo } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];

interface DashboardCounts {
  members_pending_payment: number;
  members_active: number;
  members_expiring: number;
  members_expired: number;
  income_month_cop: number | null;
}

/** "1.250": el separador de miles de formatCount y formatCop. */
const miles = (value: number): string => String(value).replace(/\B(?=(\d{3})+(?!\d))/g, ".");

/** S4B-F1 (S4B-D88): el límite de la grilla de socios tras el clic en un KPI. */
const GRID_BUDGET_MS = 10_000;

/**
 * S4B-F1 (S4B-D88): lectura de solo SELECT sobre la base del ensayo con `docker exec <contenedor> psql`.
 * E2E_DB_CONTAINER (por ejemplo apex-ensayo-db-1), E2E_DB_USER y E2E_DB_NAME (apex_ensayo) los fija V4.
 */
function psqlEscalar(sql: string): number {
  const contenedor = process.env.E2E_DB_CONTAINER ?? "";
  if (!/^[A-Za-z0-9][A-Za-z0-9_.-]*$/.test(contenedor)) {
    throw new Error("E2E_DB_CONTAINER no es un nombre de contenedor válido (letras, dígitos, punto, guion y guion bajo).");
  }
  const usuario = process.env.E2E_DB_USER ?? "apex";
  const base = process.env.E2E_DB_NAME ?? "apex_ensayo";
  const salida = execFileSync("docker", ["exec", "-i", contenedor, "psql", "-U", usuario, "-d", base, "-At", "-c", sql], { encoding: "utf8" });
  return Number(salida.trim());
}

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

  test("los KPI de Inicio coinciden con GET /dashboard y con psql sobre la base del ensayo", async ({ page }) => {
    test.skip(process.env.E2E_DB_CONTAINER === undefined, "necesita E2E_DB_CONTAINER (el contenedor de la base del ensayo, V4)");
    exigirStackLocal(process.env.E2E_BASE_URL);
    await page.setViewportSize({ width: 1440, height: 900 });
    const token = await loginComo(page, datosDeBase());
    await page.goto("/");
    await expect(page.getByRole("link", { name: /^Socios al día: / })).toBeVisible();
    const api = await dashboardPorApi(page, token);

    // Pendientes de pago: socios cuya membresía que decide (US-092: vigente > pendiente > vencida > futura)
    // es una pendiente, es decir con una pendiente y sin otra membresía vigente (ni cancelada, ni
    // pendiente, ni vencida por fecha o sin clases, y ya iniciada) en la fecha de hoy de Bogotá.
    // V5: solo socios no dados de baja (el api no cuenta a los dados de baja; las specs de venta dejan socios de baja con pendientes).
    const pendientes = psqlEscalar(
      "WITH h AS (SELECT (now() AT TIME ZONE 'America/Bogota')::date AS hoy) SELECT count(DISTINCT m.member_id) FROM memberships.memberships m JOIN members.members s ON s.id = m.member_id, h WHERE s.deleted_at IS NULL AND m.status = 'pending_payment' AND NOT EXISTS (SELECT 1 FROM memberships.memberships c WHERE c.member_id = m.member_id AND c.status NOT IN ('cancelled', 'pending_payment') AND c.end_date >= h.hoy AND c.classes_remaining IS DISTINCT FROM 0 AND c.start_date <= h.hoy)",
    );
    expect(api.members_pending_payment).toBe(pendientes);
    // Ingresos del mes de Bogotá: pagos no anulados.
    const ingresos = psqlEscalar(
      "SELECT coalesce(sum(amount_cop), 0) FROM payments.payments WHERE NOT voided AND paid_at >= date_trunc('month', now() AT TIME ZONE 'America/Bogota') AT TIME ZONE 'America/Bogota'",
    );
    expect(api.income_month_cop).toBe(ingresos);
    await expect(page.getByRole("link", { name: `Socios al día: ${miles(api.members_active)}` })).toBeVisible();
    await expect(page.getByRole("link", { name: `Por vencer: ${miles(api.members_expiring)}` })).toBeVisible();
    await expect(page.getByRole("link", { name: `Vencidos: ${miles(api.members_expired)}` })).toBeVisible();
    await expect(page.getByRole("link", { name: new RegExp(`^${miles(api.members_pending_payment)} socios? con pago pendiente`) })).toBeVisible();
  });

  test("Por vencer lleva a /socios?membership_status=expiring y la grilla de socios aparece en menos de 10 s", async ({ page }) => {
    exigirStackLocal(process.env.E2E_BASE_URL);
    await page.setViewportSize({ width: 1440, height: 900 });
    const token = await loginComo(page, datosDeBase());
    await page.goto("/");
    await expect(page.getByRole("link", { name: /^Por vencer: / })).toBeVisible();
    const api = await dashboardPorApi(page, token);

    const inicio = Date.now();
    await page.getByRole("link", { name: `Por vencer: ${miles(api.members_expiring)}` }).click();
    await expect.poll(() => new URL(page.url()).pathname).toBe("/socios");
    expect(new URL(page.url()).searchParams.get("membership_status")).toBe("expiring");
    await expect(page.getByRole("table")).toBeVisible({ timeout: GRID_BUDGET_MS });
    expect(Date.now() - inicio).toBeLessThan(GRID_BUDGET_MS);
  });

  test("el member que abre / termina en /mi sin ver el tablero", async ({ page }) => {
    test.skip(process.env.E2E_MEMBER_EMAIL === undefined || process.env.E2E_MEMBER_PASSWORD === undefined, "necesita E2E_MEMBER_EMAIL y E2E_MEMBER_PASSWORD (un usuario con rol member del ensayo, V4)");
    exigirStackLocal(process.env.E2E_BASE_URL);
    await loginComo(page, { email: process.env.E2E_MEMBER_EMAIL ?? "", password: process.env.E2E_MEMBER_PASSWORD ?? "" });

    await page.goto("/");

    await expect.poll(() => new URL(page.url()).pathname).toBe("/mi");
    await expect(page.getByRole("link", { name: /^Socios al día: / })).toHaveCount(0);
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
