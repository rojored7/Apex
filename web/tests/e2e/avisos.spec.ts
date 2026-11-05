// S5-F1 (US-127, US-128, US-129) contra `vite preview`: /avisos/hoy en un navegador real con el api
// simulado por page.route. "Abrir WhatsApp" hace el POST y solo entonces abre wa.me con
// noopener,noreferrer (window.open observado); "Omitir" pide el motivo; axe-core en claro y oscuro a
// 390 y 1440 px, sin desborde y con capturas. La variante contra el stack es stack/avisos.spec.ts.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";
import { mockSession } from "./helpers/session";

const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const ADMIN_ID = "11111111-1111-4111-8111-111111111111";
const WA_URL = "https://wa.me/573201234567?text=Hola%20Juan";

const aviso = (n: number, extra: Record<string, unknown>) => ({
  id: `0000000${String(n)}-1111-4111-8111-111111111111`,
  rule_id: "aaaaaaaa-0000-4000-8000-000000000001",
  member_id: `0000000${String(n)}-2222-4222-8222-222222222222`,
  member_name: "Socio",
  membership_id: `0000000${String(n)}-3333-4333-8333-333333333333`,
  target_date: "2026-10-20",
  channel: "whatsapp_link",
  status: "pending",
  rendered_subject: "Tu plan vence hoy",
  rendered_body: "Hola, tu plan vence hoy.",
  attempts: 0,
  last_error: null,
  sent_at: null,
  sent_by: null,
  skip_reason: null,
  created_at: "2026-10-20T12:00:00Z",
  updated_at: "2026-10-20T12:00:00Z",
  ...extra,
});

const JUAN = aviso(1, { member_name: "Juan Pérez", rendered_body: "Hola Juan, tu plan Trimestral en APEX vence hoy." });
const CAMILA = aviso(2, { member_name: "Camila Torres", target_date: "2026-10-15", rendered_body: "Hola Camila, tu plan Mensual venció." });
const ANDRES = aviso(3, { member_name: "Andrés Ruiz", channel: "email", status: "failed", last_error: "timeout", attempts: 3, rendered_body: "Hola Andrés, te quedan 2 clases." });

const json = (route: Route, status: number, body?: unknown) =>
  route.fulfill({ status, contentType: "application/json", body: body === undefined ? "" : JSON.stringify(body) });

interface FakeApi {
  waCalls: string[];
  skipBodies: Record<string, unknown>[];
}

async function fakeApi(page: Page): Promise<FakeApi> {
  const state: FakeApi = { waCalls: [], skipBodies: [] };
  const closed = new Set<string>();
  await mockSession(page, { id: ADMIN_ID, email: "admin@apex.test", role: "admin" });
  await page.route(/\/api\/v1\/notifications\/today(\?.*)?$/, (route) => {
    const url = new URL(route.request().url());
    const items = [JUAN, CAMILA, ANDRES].filter((row) => !closed.has(row.id));
    return json(route, 200, { items, total: items.length, limit: Number(url.searchParams.get("limit")), offset: Number(url.searchParams.get("offset")) });
  });
  await page.route(/\/api\/v1\/notifications\/[0-9a-f-]+\/wa-link$/, (route) => {
    const id = new URL(route.request().url()).pathname.split("/").at(-2) ?? "";
    state.waCalls.push(id);
    closed.add(id);
    return json(route, 200, { url: WA_URL });
  });
  await page.route(/\/api\/v1\/notifications\/[0-9a-f-]+\/skip$/, (route) => {
    const id = new URL(route.request().url()).pathname.split("/").at(-2) ?? "";
    state.skipBodies.push(route.request().postDataJSON() as Record<string, unknown>);
    closed.add(id);
    return json(route, 200, { ...CAMILA, status: "skipped", skip_reason: "Ya pagó" });
  });
  // window.open observado: nada sale del navegador de la prueba.
  await page.addInitScript(() => {
    const opened: unknown[][] = [];
    (window as unknown as { __opened: unknown[][] }).__opened = opened;
    window.open = (...args: unknown[]) => {
      opened.push(args);
      return null;
    };
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

async function expectNoOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

async function open(page: Page, theme: "light" | "dark", width: number): Promise<void> {
  await page.setViewportSize({ width, height: 900 });
  await page.emulateMedia({ colorScheme: theme });
  await page.addInitScript((t) => {
    localStorage.setItem("apex.theme", t);
  }, theme);
  await page.goto("/avisos/hoy");
}

for (const [theme, width] of [
  ["light", 1440],
  ["dark", 390],
  ["light", 390],
  ["dark", 1440],
] as const) {
  test(`Por avisar hoy en ${theme} a ${String(width)} px pasa axe, no desborda y tiene captura`, async ({ page }) => {
    await fakeApi(page);
    await open(page, theme, width);

    await expect(page.getByRole("heading", { level: 1, name: /^Por avisar hoy · / })).toBeVisible();
    await expect(page.getByText("3 por atender: 2 esperan WhatsApp, 1 es de correo.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Abrir WhatsApp de Juan Pérez" })).toBeVisible();
    await expect(page.getByText("Correo: falló · tiempo agotado")).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);
    await expectNoOverflow(page);
    const box = await page.getByRole("button", { name: "Abrir WhatsApp de Juan Pérez" }).boundingBox();
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
    await page.screenshot({ path: `test-results/captures/avisos-hoy-${theme}-${String(width)}.png`, fullPage: true });
  });
}

test("Abrir WhatsApp hace el POST, abre wa.me con noopener,noreferrer y avisa que quedó enviado", async ({ page }) => {
  const api = await fakeApi(page);
  await open(page, "light", 1440);

  await page.getByRole("button", { name: "Abrir WhatsApp de Juan Pérez" }).click();

  await expect(page.getByText("WhatsApp abierto para Juan Pérez. El aviso quedó marcado como enviado.")).toBeVisible();
  expect(api.waCalls).toEqual([JUAN.id]);
  const opened = await page.evaluate(() => (window as unknown as { __opened: unknown[][] }).__opened);
  expect(opened).toEqual([[WA_URL, "_blank", "noopener,noreferrer"]]);
  await expect(page.getByRole("link", { name: "Juan Pérez" })).toHaveCount(0);
  expect(await page.content()).not.toContain("573201234567");
});

test("Omitir pide un motivo de al menos 3 caracteres y envía el POST", async ({ page }) => {
  const api = await fakeApi(page);
  await open(page, "dark", 390);

  await page.getByRole("button", { name: "Omitir aviso de Camila Torres" }).click();
  const dialog = page.getByRole("dialog", { name: "¿Omitir el aviso de Camila Torres?" });
  await expect(dialog.getByRole("button", { name: "Omitir aviso" })).toBeDisabled();
  await dialog.getByRole("textbox", { name: /^Motivo/ }).fill("Ya pagó");
  expect(await axeViolations(page)).toEqual([]);
  await dialog.getByRole("button", { name: "Omitir aviso" }).click();

  await expect(page.getByText("Aviso de Camila Torres omitido. Quedó en el historial con tu motivo.")).toBeVisible();
  expect(api.skipBodies).toEqual([{ reason: "Ya pagó" }]);
});
