// S3-F1 (US-073 a US-076; demo 6 por la pantalla) contra el stack de Compose (proyecto `stack`,
// S3-D72): el admin crea por el api un socio con documento y teléfono aleatorios, abre la ficha,
// "Mostrar" el documento (aparece y se re-enmascara al ocultar), edita el teléfono por la pantalla,
// lo da de baja (ficha de solo lectura) y lo reactiva; un coach, en otra sesión, ve la ficha sin
// "Dar de baja". axe en cada paso y capturas de la ficha en claro y oscuro. Al terminar da de baja
// al socio por el api (baja lógica). Un login por rol y corrida: el de login es por IP (5 por minuto).
// Credenciales: E2E_ADMIN_EMAIL y E2E_ADMIN_PASSWORD (un admin); el coach sale de E2E_COACH_EMAIL y
// E2E_COACH_PASSWORD o, sin ellas, se crea uno por el api con su enlace de activación (crearCoach).
// Sin E2E_BASE_URL se omite.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { borrarUsuario, capture, crearCoach, datosDeBase, documentoAleatorio, esperarTransiciones, loginComo, sameOriginHeaders, type Credentials } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const API = "/api/v1";

interface SocioDeFicha {
  id: string;
  nombre: string;
  documento: string;
}

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

/** Un teléfono celular de 10 dígitos al azar (empieza por 3). */
function telefonoAleatorio(): string {
  return `3${documentoAleatorio().slice(1)}`;
}

async function crearSocioConContacto(page: Page, token: string): Promise<SocioDeFicha> {
  const documento = documentoAleatorio();
  const apellido = `Ficha${Date.now().toString(36)}`;
  const created = await page.request.post(`${API}/members`, {
    headers: { ...sameOriginHeaders(), Authorization: `Bearer ${token}` },
    data: { first_name: "Sofía", last_name: apellido, document_type: "CC", document: documento, phone: telefonoAleatorio(), data_consent: true },
  });
  if (!created.ok()) throw new Error(`POST /members respondió ${String(created.status())}.`);
  const body = (await created.json()) as { id: string };
  return { id: body.id, nombre: `Sofía ${apellido}`, documento };
}

function coachDeEntorno(): Credentials | null {
  const email = process.env.E2E_COACH_EMAIL;
  const password = process.env.E2E_COACH_PASSWORD;
  return email && password ? { email, password } : null;
}

test.describe("ficha del socio contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con B9b y B10");

  let socio: SocioDeFicha | null = null;
  // Un solo login del admin por corrida (el límite de login es por IP: 5 por minuto en dev).
  let token = "";

  test.afterEach(async ({ page }) => {
    if (socio) await page.request.delete(`${API}/members/${socio.id}`, { headers: { ...sameOriginHeaders(), Authorization: `Bearer ${token}` } });
    socio = null;
  });

  test("el admin revela, edita el teléfono, da de baja y reactiva; el coach no ve Dar de baja", async ({ page, browser }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const admin = datosDeBase();
    token = await loginComo(page, admin);
    socio = await crearSocioConContacto(page, token);
    const ultimos = socio.documento.slice(-4);

    // US-073: la ficha con los sensibles enmascarados por el api.
    await page.goto(`/socios/${socio.id}`);
    await expect(page.getByRole("heading", { level: 1, name: new RegExp(socio.nombre) })).toBeVisible();
    const datos = page.getByRole("tabpanel");
    await expect(datos.getByText(`CC •••• ${ultimos}`)).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);
    await capture(page, "ficha-socio-stack", "light", 1440);
    await page.emulateMedia({ colorScheme: "dark" });
    expect(await axeViolations(page)).toEqual([]);
    await capture(page, "ficha-socio-stack", "dark", 1440);
    await page.emulateMedia({ colorScheme: "light" });

    // US-074: Mostrar el documento (una llamada auditada) y Ocultar.
    const reveals: string[] = [];
    page.on("request", (request) => {
      if (request.method() === "POST" && new URL(request.url()).pathname === `${API}/members/${socio?.id ?? ""}/reveal`) reveals.push(request.postData() ?? "");
    });
    // Documento es el primer campo de "Datos de contacto" (Socio_Ficha.html).
    await datos.getByRole("button", { name: "Mostrar" }).first().click();
    await expect(datos.getByText(socio.documento, { exact: true })).toBeVisible();
    expect(reveals).toEqual([JSON.stringify({ field: "document" })]);
    await datos.getByRole("button", { name: "Ocultar" }).click();
    await expect(datos.getByText(`CC •••• ${ultimos}`)).toBeVisible();
    expect(await page.content()).not.toContain(socio.documento);
    const almacenado = await page.evaluate(() =>
      [localStorage, sessionStorage].flatMap((s) => Array.from({ length: s.length }, (_, i) => `${s.key(i) ?? ""}=${s.getItem(s.key(i) ?? "") ?? ""}`)).join(" | "),
    );
    expect(almacenado).not.toContain(socio.documento);

    // US-075: editar el teléfono por la pantalla (solo viaja `phone`).
    const telefono = telefonoAleatorio();
    const patches: string[] = [];
    page.on("request", (request) => {
      if (request.method() === "PATCH") patches.push(request.postData() ?? "");
    });
    await page.getByRole("link", { name: "Editar" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Editar socio" })).toBeVisible();
    const grupoTelefono = page.getByRole("group", { name: "Teléfono (WhatsApp)" });
    await grupoTelefono.getByRole("button", { name: "Cambiar" }).click();
    await grupoTelefono.getByRole("textbox", { name: /^Nuevo teléfono/ }).fill(telefono);
    expect(await axeViolations(page)).toEqual([]);
    await page.getByRole("button", { name: "Guardar cambios" }).click();
    await expect(page.getByText("Cambios guardados")).toBeVisible();
    await expect(datos.getByText(`••• ••• ${telefono.slice(-4)}`)).toBeVisible();
    expect(patches).toEqual([JSON.stringify({ phone: telefono })]);
    // S4A-F2 (US-106): la caja "Historial reciente" de Datos cuenta la edición sin el número.
    const reciente = page.getByRole("complementary", { name: "Historial" });
    await expect(reciente.getByText(/ editó teléfono$/)).toBeVisible();
    await expect(reciente.getByText(/ mostró el documento$/)).toBeVisible();
    await expect(reciente).not.toContainText(telefono);

    // US-076: dar de baja (solo lectura) y reactivar.
    await page.getByRole("button", { name: "Dar de baja" }).click();
    const baja = page.getByRole("dialog", { name: `¿Dar de baja a ${socio.nombre}?` });
    expect(await axeViolations(page)).toEqual([]);
    await baja.getByRole("button", { name: "Dar de baja" }).click();
    await expect(page.getByText("Socio dado de baja")).toBeVisible();
    await expect(page.getByText(/Dado de baja el /)).toBeVisible();
    await expect(page.getByRole("link", { name: "Editar" })).toHaveCount(0);
    expect(await axeViolations(page)).toEqual([]);
    await capture(page, "ficha-socio-baja-stack", "light", 1440);

    await page.getByRole("button", { name: "Reactivar" }).click();
    await page.getByRole("dialog", { name: `¿Reactivar a ${socio.nombre}?` }).getByRole("button", { name: "Reactivar" }).click();
    await expect(page.getByText("Socio reactivado")).toBeVisible();
    await expect(page.getByRole("link", { name: "Editar" })).toBeVisible();

    // Otra sesión: el coach ve la ficha y "Editar", pero no "Dar de baja".
    // Fase 4 L9: el coach que crea la spec se borra al final; el del entorno no.
    const coachFijo = coachDeEntorno();
    const coach: Credentials & { id?: string } = coachFijo ?? (await crearCoach(page, admin));
    const creadoId = coachFijo ? null : (coach.id ?? null);
    const context = await browser.newContext({ baseURL: process.env.E2E_BASE_URL ?? "" });
    try {
      const coachPage = await context.newPage();
      await loginComo(coachPage, coach);
      await coachPage.goto(`/socios/${socio.id}`);
      await expect(coachPage.getByRole("heading", { level: 1, name: new RegExp(socio.nombre) })).toBeVisible();
      await expect(coachPage.getByRole("link", { name: "Editar" })).toBeVisible();
      await expect(coachPage.getByRole("button", { name: "Dar de baja" })).toHaveCount(0);
      await expect(coachPage.getByRole("button", { name: "Reactivar" })).toHaveCount(0);
      // S4A-F2 (US-106): el coach abre la pestaña Historial (members.history.view).
      await coachPage.getByRole("tab", { name: "Historial" }).click();
      await expect(coachPage.getByRole("tabpanel").getByText(/ mostró el documento$/).first()).toBeVisible();
      await expect(coachPage.getByRole("tabpanel")).not.toContainText(socio.documento);
    } finally {
      await context.close();
      if (creadoId) await borrarUsuario(page, creadoId, admin);
    }
  });
});
