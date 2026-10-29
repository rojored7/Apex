// S4A-F1 (US-102 a US-104) contra `vite preview`: /sistema/auditoria en un navegador real con el api
// simulado por page.route (enmienda E8: esta captura en preview se crea en el Rojo de F1). Filtros en
// la URL con los nombres del api, detalle por `?seq=` sin ninguna acción de descifrar, "Verificar
// ahora" con 202 y sondeo de GET /audit/verify/last, y el coach en "Sin permiso". axe-core en claro y
// oscuro a 320, 768, 1024 y 1440 px (S4A-V4, como home.spec.ts), sin desborde horizontal y con
// capturas. La variante real es stack/audit.spec.ts.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";
import { json, mockSession } from "./helpers/session";

const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const WIDTHS = [320, 768, 1024, 1440] as const;
const ADMIN = { id: "11111111-1111-4111-8111-111111111111", email: "admin@apex.test", role: "admin" } as const;
const COACH = { id: "22222222-2222-4222-8222-222222222222", email: "coach@apex.test", role: "coach" } as const;
const SYSTEM = "00000000-0000-0000-0000-000000000001";
const LAURA = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const KEY = "5f0c2a7e-1b3d-4c5e-8f9a-0b1c2d3e4f5a";

const row = (overrides: Record<string, unknown>) => ({
  seq: 88412,
  at: "2026-10-20T16:52:08Z",
  user_id: ADMIN.id,
  user_email: ADMIN.email,
  user_name: "admin",
  action: "update",
  table_name: "members.members",
  record_id: LAURA,
  subject_member_id: LAURA,
  ...overrides,
});

const ROWS = [
  row({}),
  row({ seq: 88411, at: "2026-10-20T19:10:00Z", user_id: COACH.id, user_email: COACH.email, user_name: "coach", action: "insert", table_name: "payments.payments", record_id: "99999999-9999-4999-8999-999999999999" }),
  row({ seq: 88410, at: "2026-10-20T12:00:00Z", user_id: SYSTEM, user_email: "system@apex.local", user_name: "system", table_name: "memberships.memberships", record_id: "66666666-6666-4666-8666-666666666666" }),
];

const marker = { encrypted: true, key_id: KEY, alg: "A256GCM" };
const DETAIL = {
  ...ROWS[0],
  before: { phone: marker, notes: "Llamar en la tarde" },
  after: { phone: marker, notes: "<script>alert(1)</script>" },
  prev_hash: "a".repeat(64),
  hash: "b".repeat(64),
  changes: [
    { field: "phone", kind: "changed", before: marker, after: marker, encrypted: true },
    { field: "notes", kind: "changed", before: "Llamar en la tarde", after: "<script>alert(1)</script>", encrypted: false },
  ],
};

const verification = (finished: string, rows = 3418) => ({
  ok: true,
  rows_checked: rows,
  through_seq: 88412,
  broken_at_seq: null,
  started_at: finished,
  finished_at: finished,
  triggered_by: ADMIN.id,
  source: "api",
});

interface FakeAudit {
  listQueries: URLSearchParams[];
  finishVerification: () => void;
}

async function fakeAudit(page: Page): Promise<FakeAudit> {
  const listQueries: URLSearchParams[] = [];
  let last = verification("2026-10-21T15:00:02Z");
  await page.route((url) => url.pathname === "/api/v1/users", (route: Route) => json(route, 200, { items: [], total: 0, limit: 200, offset: 0 }));
  await page.route("**/api/v1/audit**", (route: Route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/v1/audit") {
      listQueries.push(url.searchParams);
      return json(route, 200, { items: ROWS, total: ROWS.length, limit: Number(url.searchParams.get("limit")), offset: Number(url.searchParams.get("offset")) });
    }
    if (url.pathname === "/api/v1/audit/verify/last") return json(route, 200, last);
    if (url.pathname === "/api/v1/audit/verify") return json(route, 202, { status: "running", last });
    if (url.pathname === "/api/v1/audit/88412") return json(route, 200, DETAIL);
    return json(route, 404, { error: { code: "audit_entry_not_found", message: "x" } });
  });
  return {
    listQueries,
    finishVerification: () => {
      last = verification("2026-10-21T16:04:00Z", 5000);
    },
  };
}

async function axeViolations(page: Page): Promise<string[]> {
  await page.evaluate(async () => {
    await Promise.all(document.getAnimations().map((animation) => animation.finished.catch(() => undefined)));
  });
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

const noHorizontalOverflow = (page: Page): Promise<boolean> => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

test.describe("auditoría (preview)", () => {
  test("el admin filtra con los nombres del api, abre el detalle sin descifrar y verifica con sondeo", async ({ page }) => {
    await mockSession(page, ADMIN);
    const api = await fakeAudit(page);
    await page.setViewportSize({ width: 1440, height: 900 });

    await page.goto("/sistema/auditoria?from=2026-10-13&to=2026-10-20");
    const table = page.getByRole("table", { name: "Auditoría" });
    await expect(table).toBeVisible();
    await expect.poll(() => api.listQueries.at(-1)?.get("from")).toBe("2026-10-13T05:00:00.000Z");
    expect(api.listQueries.at(-1)?.get("to")).toBe("2026-10-21T05:00:00.000Z");

    await page.getByRole("combobox", { name: "Entidad" }).selectOption({ label: "Pago" });
    await expect.poll(() => api.listQueries.at(-1)?.get("table")).toBe("payments.payments");
    expect(new URL(page.url()).searchParams.get("table")).toBe("payments.payments");

    await table.getByRole("link", { name: "20 oct 2026, 11:52 a. m." }).click();
    const panel = page.getByRole("dialog", { name: "Entrada #88412" });
    await expect(panel).toBeVisible();
    await expect(panel.getByText(`Cifrado · llave ${KEY}`).first()).toBeVisible();
    await expect(panel.getByText("<script>alert(1)</script>", { exact: false })).toBeVisible();
    await expect(panel.getByRole("button", { name: /mostrar|descifrar/i })).toHaveCount(0);
    await panel.getByRole("button", { name: "Cerrar", exact: true }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);

    await page.getByRole("button", { name: "Verificar ahora" }).click();
    await expect(page.getByText("Verificando la cadena en segundo plano…")).toBeVisible();
    api.finishVerification();
    await expect(page.getByText(/^Cadena íntegra: 5\.000 filas verificadas/)).toBeVisible({ timeout: 15_000 });
  });

  for (const scheme of ["light", "dark"] as const) {
    for (const width of WIDTHS) {
      test(`lista y detalle sin violaciones de axe en ${scheme} a ${String(width)} px`, async ({ page }, testInfo) => {
        await page.emulateMedia({ colorScheme: scheme });
        await page.setViewportSize({ width, height: 900 });
        await mockSession(page, ADMIN);
        await fakeAudit(page);

        await page.goto("/sistema/auditoria");
        await expect(page.getByRole("heading", { level: 1, name: /Auditoría/ })).toBeVisible();
        await expect(page.getByText(/^Última verificación/)).toBeVisible();
        expect(await axeViolations(page)).toEqual([]);
        expect(await noHorizontalOverflow(page)).toBe(true);
        await page.screenshot({ path: testInfo.outputPath(`auditoria-${scheme}-${String(width)}.png`), fullPage: true });

        await page.goto("/sistema/auditoria?seq=88412");
        await expect(page.getByRole("dialog", { name: "Entrada #88412" })).toBeVisible();
        await expect(page.getByRole("list", { name: "Cambios" })).toBeVisible();
        expect(await axeViolations(page)).toEqual([]);
        await page.screenshot({ path: testInfo.outputPath(`auditoria-detalle-${scheme}-${String(width)}.png`), fullPage: true });
      });
    }
  }

  test("el coach que abre /sistema/auditoria ve Sin permiso y el menú no muestra Auditoría", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockSession(page, COACH);
    let asked = false;
    await page.route("**/api/v1/audit**", (route: Route) => {
      asked = true;
      return json(route, 403, { error: { code: "forbidden", message: "x" } });
    });

    await page.goto("/sistema/auditoria");

    await expect(page.getByRole("heading", { level: 1, name: "Sin permiso" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Menú principal" }).getByRole("link", { name: "Auditoría" })).toHaveCount(0);
    expect(asked).toBe(false);
  });
});
