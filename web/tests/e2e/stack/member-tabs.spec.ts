// S3-F7 (US-093 y US-101; demo 6, botones de la ficha) contra el stack de Compose (proyecto `stack`,
// S3-D72): el admin crea por el api un socio y un plan y vende con un abono de 60.000; en la ficha,
// la pestaña Membresías muestra la vigente "Pendiente de pago" con su saldo y "Registrar saldo" abre
// el panel de pagos (?pago=<membresía>) con el saldo precargado (y la confirmación del posible
// duplicado, S3-D41, porque el abono de la venta es igual y reciente); tras registrarlo la tarjeta queda
// "Al día". La pestaña Pagos lista los dos pagos (el más reciente primero), el admin anula uno con
// motivo ("Anulado" y "Motivo: …") y "Ocultar anulados" lo quita (voided=false). axe en cada paso y
// capturas en claro y oscuro. Un solo login del admin por corrida (el login es por IP: 5 por minuto
// en dev) y las altas van con ese token. Al terminar da de baja al socio (baja lógica).
// Credenciales: E2E_ADMIN_EMAIL y E2E_ADMIN_PASSWORD. Sin E2E_BASE_URL se omite.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { capture, datosDeBase, documentoAleatorio, esperarTransiciones, loginComo, sameOriginHeaders } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const API = "/api/v1";
const REASON = "Registro duplicado en la prueba";

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

async function post<T>(page: Page, token: string, path: string, data: unknown): Promise<T> {
  const response = await page.request.post(`${API}${path}`, { headers: { ...sameOriginHeaders(), Authorization: `Bearer ${token}` }, data });
  if (!response.ok()) throw new Error(`POST ${path} respondió ${String(response.status())}.`);
  return (await response.json()) as T;
}

test.describe("pestañas Membresías y Pagos de la ficha contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con B11 y S3-F7");

  let socioId: string | null = null;
  let token = "";

  test.afterEach(async ({ page }) => {
    if (socioId) await page.request.delete(`${API}/members/${socioId}`, { headers: { ...sameOriginHeaders(), Authorization: `Bearer ${token}` } });
    socioId = null;
  });

  test("la vigente con abono, Registrar saldo por el panel, anular un pago y ocultar los anulados", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    token = await loginComo(page, datosDeBase());
    const sufijo = Date.now().toString(36);
    const socio = await post<{ id: string }>(page, token, "/members", { first_name: "Tomás", last_name: `Pestanas${sufijo}`, document_type: "CC", document: documentoAleatorio(), data_consent: true });
    socioId = socio.id;
    const planName = `Mensual ${sufijo}`;
    const plan = await post<{ id: string }>(page, token, "/plans", { name: planName, price_cop: 120_000, kind: "days", duration_days: 30 });
    const venta = await post<{ id: string; status: string }>(page, token, `/members/${socio.id}/memberships`, { plan_id: plan.id, first_payment: { amount_cop: 60_000, method: "cash" } });
    expect(venta.status).toBe("pending_payment");

    // US-093: la pestaña Membresías desde la ficha.
    await page.goto(`/socios/${socio.id}`);
    await page.getByRole("tab", { name: "Membresías" }).click();
    await expect(page).toHaveURL(new RegExp(`/socios/${socio.id}/membresias$`));
    const vigente = page.getByRole("region", { name: "Membresía vigente" });
    await expect(vigente.getByText("Pendiente de pago")).toBeVisible();
    await expect(vigente.getByText(planName)).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);
    await capture(page, "ficha-membresias-stack", "light", 1440);
    await capture(page, "ficha-membresias-stack", "dark", 1440);
    await page.emulateMedia({ colorScheme: "light" });

    // Registrar saldo: el panel de pagos sobre la pestaña con el saldo precargado.
    await vigente.getByRole("link", { name: `Registrar saldo de la membresía ${planName}` }).click();
    await expect(page).toHaveURL(new RegExp(`\\?pago=${venta.id}$`));
    const panel = page.getByRole("dialog", { name: "Registrar pago" });
    await expect(panel.getByRole("textbox", { name: /^Valor recibido/ })).toHaveValue("$ 60.000");
    expect(await axeViolations(page)).toEqual([]);
    await panel.getByRole("button", { name: "Registrar" }).click();
    // S3-D41: el abono de la venta (mismo valor, medio y quien registra, hace segundos) hace que el api
    // pida confirmar el posible duplicado (409 payment_possible_duplicate); se confirma.
    const duplicado = page.getByRole("dialog", { name: "¿Registrar otro pago igual?" });
    await expect(duplicado).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);
    await duplicado.getByRole("button", { name: "Sí, registrar otro" }).click();
    await expect(panel.getByRole("status", { name: "Pago registrado" })).toBeVisible();
    await panel.getByRole("button", { name: "Cerrar" }).first().click();
    await expect(page).not.toHaveURL(/pago=/);
    await expect(vigente.getByText("Al día")).toBeVisible();
    await expect(vigente.getByRole("link", { name: /^Registrar saldo/ })).toHaveCount(0);

    // US-101: la pestaña Pagos, el más reciente primero; el admin anula uno con motivo.
    await page.getByRole("tab", { name: "Pagos" }).click();
    await expect(page).toHaveURL(new RegExp(`/socios/${socio.id}/pagos$`));
    const tabla = page.getByRole("region", { name: "Pagos del socio" });
    await expect(tabla.getByRole("row")).toHaveCount(3);
    expect(await axeViolations(page)).toEqual([]);
    await tabla.getByRole("button", { name: /^Anular el pago/ }).first().click();
    const anular = page.getByRole("dialog", { name: "¿Anular este pago?" });
    await anular.getByRole("textbox", { name: /^Motivo/ }).fill(REASON);
    await anular.getByRole("button", { name: "Anular pago" }).click();
    await page.getByRole("dialog", { name: "Pago anulado" }).getByRole("button", { name: "Cerrar" }).click();
    await expect(tabla.getByText(`Motivo: ${REASON}`)).toBeVisible();
    await expect(tabla.getByRole("button", { name: /^Anular el pago/ })).toHaveCount(1);
    expect(await axeViolations(page)).toEqual([]);
    await capture(page, "ficha-pagos-stack", "light", 1440);
    await capture(page, "ficha-pagos-stack", "dark", 1440);
    await page.emulateMedia({ colorScheme: "light" });

    // Ocultar anulados: voided=false en la URL y en la petición.
    const filtrada = page.waitForResponse((r) => new URL(r.url()).pathname === `${API}/members/${socio.id}/payments` && new URL(r.url()).searchParams.get("voided") === "false");
    await page.getByRole("checkbox", { name: "Ocultar anulados" }).click();
    await filtrada;
    await expect(page).toHaveURL(/voided=false/);
    await expect(tabla.getByRole("row")).toHaveCount(2);
    await expect(tabla.getByText(`Motivo: ${REASON}`)).toHaveCount(0);
    await capture(page, "ficha-pagos-stack-movil", "light", 390);
  });
});
