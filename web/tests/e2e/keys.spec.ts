// S6-F2 (US-143 a US-146) contra `vite preview`: /sistema/llaves en un navegador real con el api simulado por
// page.route. Inventario sin material de llave, «Rotar» solo en filas activas de cifrado, modal con ROTAR
// exacto y salto a Trabajos, bitácora con el rango de fechas, CBOM descargado y el coach en «Sin permiso».
// axe-core en claro y oscuro a 320, 768, 1024 y 1440 px, sin desborde horizontal y con capturas. La variante
// real es stack/keys-rotate.spec.ts.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";
import { json, mockSession } from "./helpers/session";

const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const WIDTHS = [320, 768, 1024, 1440] as const;
const ADMIN = { id: "11111111-1111-4111-8111-111111111111", email: "admin@apex.test", role: "admin" } as const;
const COACH = { id: "22222222-2222-4222-8222-222222222222", email: "coach@apex.test", role: "coach" } as const;
const PHONE_KEY = "22222222-2222-4222-8222-aaaaaaaaaaaa";
const JOB = "77777777-7777-4777-8777-777777777777";

const key = (overrides: Record<string, unknown>) => ({
  id: "11111111-1111-4111-8111-111111111111",
  purpose: "encrypt",
  data_class: "member.document",
  algorithm: "A256GCM",
  version: 2,
  state: "active",
  provider: "openbao",
  created_at: "2026-03-02T15:00:00Z",
  rotated_at: "2026-10-18T18:00:00Z",
  age_days: 255,
  records_count: 342,
  ...overrides,
});

const KEYS = [
  key({}),
  key({ id: "11111111-1111-4111-8111-111111111112", version: 1, state: "decrypt_only", rotated_at: null, records_count: 12 }),
  key({ id: PHONE_KEY, data_class: "member.phone", version: 1, rotated_at: null, age_days: 40 }),
  key({ id: "44444444-4444-4444-8444-444444444444", purpose: "index", data_class: "member.email", algorithm: "HMAC-SHA256", version: 1, rotated_at: null, records_count: null }),
  key({ id: "55555555-5555-4555-8555-555555555555", purpose: "sign", data_class: "audit.signature", algorithm: "Ed25519", version: 1, rotated_at: null, age_days: 90, records_count: null }),
];

const SUMMARY = { active_count: 4, operations_today: 1204, running_jobs: 1, provider: { names: ["openbao"], state: "ok" } };

const OPS = [
  { id: "aaaaaaaa-0000-4000-8000-000000000001", at: "2026-10-20T15:30:00Z", user_id: ADMIN.id, verb: "decrypt", data_class: "member.document", key_id: KEYS[0]?.id, key_version: 2, record_id: null, purpose: "reveal", result: "ok", batch_id: null, count: 1 },
  { id: "aaaaaaaa-0000-4000-8000-000000000002", at: "2026-10-20T12:00:00Z", user_id: "00000000-0000-0000-0000-000000000001", verb: "sign", data_class: "audit.signature", key_id: null, key_version: 1, record_id: null, purpose: null, result: "ok", batch_id: null, count: 1 },
];

const job = (status: "running" | "done") => ({
  id: JOB,
  kind: "rotate",
  data_class: "member.phone",
  status,
  total: 342,
  done: status === "done" ? 342 : 212,
  percent: status === "done" ? 100 : 61,
  started_at: "2026-10-20T14:00:00Z",
  finished_at: status === "done" ? "2026-10-20T14:05:00Z" : null,
  created_at: "2026-10-20T13:59:00Z",
});

interface FakeKeys {
  opsQueries: URLSearchParams[];
  rotations: unknown[];
  cbomRequests: () => number;
  finishJob: () => void;
}

async function fakeKeys(page: Page): Promise<FakeKeys> {
  const opsQueries: URLSearchParams[] = [];
  const rotations: unknown[] = [];
  let cbom = 0;
  let status: "running" | "done" = "running";
  await page.route("**/api/v1/crypto/**", async (route: Route) => {
    const url = new URL(route.request().url());
    const page_ = { limit: Number(url.searchParams.get("limit")), offset: Number(url.searchParams.get("offset")) };
    if (url.pathname === "/api/v1/crypto/keys") return json(route, 200, { items: KEYS, total: KEYS.length, ...page_, summary: SUMMARY });
    if (url.pathname === "/api/v1/crypto/ops") {
      opsQueries.push(url.searchParams);
      return json(route, 200, { items: OPS, total: OPS.length, ...page_ });
    }
    if (url.pathname === "/api/v1/crypto/jobs") return json(route, 200, { items: [job(status)], total: 1, ...page_ });
    if (url.pathname === `/api/v1/crypto/keys/${PHONE_KEY}/rotate`) {
      rotations.push(route.request().postDataJSON());
      return json(route, 202, { job_id: JOB, new_key_id: "88888888-8888-4888-8888-888888888888", previous_key_id: PHONE_KEY });
    }
    if (url.pathname === "/api/v1/crypto/cbom") {
      cbom += 1;
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: { "Content-Disposition": 'attachment; filename="apex-cbom-2026-10-20.json"' },
        body: JSON.stringify({ format: "apex-cbom", keys: KEYS.length }),
      });
    }
    return json(route, 404, { error: { code: "not_found", message: "x" } });
  });
  return {
    opsQueries,
    rotations,
    cbomRequests: () => cbom,
    finishJob: () => {
      status = "done";
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

test.describe("llaves (preview)", () => {
  test("el admin ve el inventario sin material, rota con ROTAR exacto, salta a Trabajos y exporta el CBOM", async ({ page }) => {
    await mockSession(page, ADMIN);
    const api = await fakeKeys(page);
    await page.setViewportSize({ width: 1440, height: 900 });

    await page.goto("/sistema/llaves");
    const table = page.getByRole("table", { name: "Inventario de llaves" });
    await expect(table.getByText("member.phone")).toBeVisible();
    await expect(page.getByText("Proveedor activo: OpenBao · conectado")).toBeVisible();
    expect(await page.content()).not.toMatch(/vault:|wrapped/);
    await expect(page.getByRole("button", { name: /^Rotar / })).toHaveCount(2);

    await page.getByRole("button", { name: "Rotar member.phone" }).click();
    const dialog = page.getByRole("dialog", { name: "¿Rotar la llave de member.phone?" });
    const confirm = dialog.getByRole("button", { name: "Rotar llave" });
    await dialog.getByLabel(/^Motivo/).fill("Rotación programada");
    await dialog.getByRole("textbox", { name: "Escribe ROTAR para confirmar" }).fill("rotar");
    await expect(confirm).toBeDisabled();
    await dialog.getByRole("textbox", { name: "Escribe ROTAR para confirmar" }).fill("ROTAR");
    await expect(confirm).toBeEnabled();
    await confirm.click();

    await expect(page.getByRole("tab", { name: "Trabajos" })).toHaveAttribute("aria-selected", "true");
    expect(api.rotations).toEqual([{ reason: "Rotación programada", confirm: "ROTAR" }]);
    const jobs = page.getByRole("table", { name: "Trabajos de rotación y recifrado" });
    await expect(jobs.getByText("61 %")).toBeVisible();
    api.finishJob();
    await expect(jobs.getByText("100 %")).toBeVisible({ timeout: 15_000 });

    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "Exportar CBOM" }).click();
    expect((await download).suggestedFilename()).toBe("apex-cbom-2026-10-20.json");
    expect(api.cbomRequests()).toBe(1);
  });

  test("la bitácora manda el rango de Bogotá en UTC y un rango inválido no viaja", async ({ page }) => {
    await mockSession(page, ADMIN);
    const api = await fakeKeys(page);
    await page.setViewportSize({ width: 1440, height: 900 });

    await page.goto("/sistema/llaves?tab=bitacora&from=2026-10-13&to=2026-10-20");
    await expect(page.getByRole("table", { name: "Bitácora de operaciones" }).getByText("Descifrar")).toBeVisible();
    await expect.poll(() => api.opsQueries.at(-1)?.get("from")).toBe("2026-10-13T05:00:00.000Z");
    expect(api.opsQueries.at(-1)?.get("to")).toBe("2026-10-21T05:00:00.000Z");

    await page.goto("/sistema/llaves?tab=bitacora&from=2026-10-20&to=2026-10-13");
    await expect(page.getByRole("alert")).toContainText("Revisa las fechas");
    await expect.poll(() => api.opsQueries.at(-1)?.has("from")).toBe(false);
  });

  for (const scheme of ["light", "dark"] as const) {
    for (const width of WIDTHS) {
      test(`inventario, bitácora, trabajos y modal sin violaciones de axe en ${scheme} a ${String(width)} px`, async ({ page }, testInfo) => {
        await page.emulateMedia({ colorScheme: scheme });
        await page.setViewportSize({ width, height: 900 });
        await mockSession(page, ADMIN);
        await fakeKeys(page);

        await page.goto("/sistema/llaves");
        await expect(page.getByRole("heading", { level: 1, name: "Llaves de cifrado" })).toBeVisible();
        await expect(page.getByText("Proveedor activo: OpenBao · conectado")).toBeVisible();
        expect(await axeViolations(page)).toEqual([]);
        expect(await noHorizontalOverflow(page)).toBe(true);
        await page.screenshot({ path: testInfo.outputPath(`llaves-${scheme}-${String(width)}.png`), fullPage: true });

        await page.getByRole("button", { name: "Rotar member.phone" }).click();
        await expect(page.getByRole("dialog", { name: "¿Rotar la llave de member.phone?" })).toBeVisible();
        expect(await axeViolations(page)).toEqual([]);
        await page.screenshot({ path: testInfo.outputPath(`llaves-modal-${scheme}-${String(width)}.png`), fullPage: true });

        // En celular las tablas son tarjetas: se espera un dato de cada pestaña, no el rol table.
        for (const [tab, dato] of [["bitacora", "Sistema (worker)"], ["trabajos", "61 %"]] as const) {
          await page.goto(`/sistema/llaves?tab=${tab}`);
          await expect(page.getByText(dato).first()).toBeVisible();
          expect(await axeViolations(page)).toEqual([]);
          expect(await noHorizontalOverflow(page)).toBe(true);
        }
      });
    }
  }

  test("el coach que abre /sistema/llaves ve Sin permiso y el menú no muestra Llaves de cifrado", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockSession(page, COACH);
    let asked = false;
    await page.route("**/api/v1/crypto/**", (route: Route) => {
      asked = true;
      return json(route, 403, { error: { code: "forbidden", message: "x" } });
    });

    await page.goto("/sistema/llaves");

    await expect(page.getByRole("heading", { level: 1, name: "Sin permiso" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Menú principal" }).getByRole("link", { name: "Llaves de cifrado" })).toHaveCount(0);
    expect(asked).toBe(false);
  });
});
