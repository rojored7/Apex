// S4A-F2 (US-106; demo del historial por la pantalla) contra el stack de Compose (proyecto `stack`):
// el admin crea por el api un socio con teléfono, le cambia el teléfono por el api (PATCH) y abre la
// pestaña Historial de la ficha: ve "<usuario> editó teléfono" y "<usuario> creó el socio", en ese
// orden, sin ninguno de los dos números. La caja "Historial reciente" de Datos muestra la misma
// edición y su enlace "Ver historial completo →" lleva a la pestaña. axe en claro y oscuro y
// capturas. Un solo login del admin por corrida (5 por minuto por IP en dev). Al terminar da de baja
// al socio por el api (baja lógica). Credenciales: E2E_ADMIN_EMAIL y E2E_ADMIN_PASSWORD. Sin
// E2E_BASE_URL se omite.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { capture, datosDeBase, documentoAleatorio, esperarTransiciones, exigirStackLocal, loginComo, sameOriginHeaders } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const API = "/api/v1";

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

/** Un teléfono celular de 10 dígitos al azar (empieza por 3). */
function telefonoAleatorio(): string {
  return `3${documentoAleatorio().slice(1)}`;
}

test.describe("historial de la ficha contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con S4A-B5 y S4A-F2");

  let socioId: string | null = null;
  let token = "";

  test.afterEach(async ({ page }) => {
    if (socioId) await page.request.delete(`${API}/members/${socioId}`, { headers: { ...sameOriginHeaders(), Authorization: `Bearer ${token}` } });
    socioId = null;
  });

  test("editar el teléfono deja 'editó teléfono' en el historial sin el número", async ({ page }) => {
    exigirStackLocal(process.env.E2E_BASE_URL);
    await page.setViewportSize({ width: 1440, height: 900 });
    token = await loginComo(page, datosDeBase());
    const headers = { ...sameOriginHeaders(), Authorization: `Bearer ${token}` };
    const telefonoViejo = telefonoAleatorio();
    const telefonoNuevo = telefonoAleatorio();
    const created = await page.request.post(`${API}/members`, {
      headers,
      data: { first_name: "Lucía", last_name: `Historial${Date.now().toString(36)}`, document_type: "CC", document: documentoAleatorio(), phone: telefonoViejo, data_consent: true },
    });
    expect(created.ok()).toBe(true);
    socioId = ((await created.json()) as { id: string }).id;
    const patched = await page.request.patch(`${API}/members/${socioId}`, { headers, data: { phone: telefonoNuevo } });
    expect(patched.ok()).toBe(true);

    // Datos: la caja "Historial reciente" con la edición y el enlace a la pestaña.
    await page.goto(`/socios/${socioId}`);
    const caja = page.getByRole("complementary", { name: "Historial" });
    await expect(caja.getByRole("heading", { name: "Historial reciente" })).toBeVisible();
    await expect(caja.getByText(/ editó teléfono$/)).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);
    await caja.getByRole("link", { name: "Ver historial completo →" }).click();

    // Historial: la edición antes que el alta, sin ninguno de los dos números.
    await expect(page).toHaveURL(new RegExp(`/socios/${socioId}/historial$`));
    await expect(page.getByRole("tab", { name: "Historial" })).toHaveAttribute("aria-selected", "true");
    const historial = page.getByRole("tabpanel").getByRole("complementary", { name: "Historial" });
    const frases = historial.locator("li b");
    await expect(frases.first()).toHaveText(/ editó teléfono$/);
    await expect(frases.last()).toHaveText(/ creó el socio$/);
    await expect(frases).toHaveCount(2);
    const contenido = await page.content();
    expect(contenido).not.toContain(telefonoViejo);
    expect(contenido).not.toContain(telefonoNuevo);
    expect(contenido).not.toContain("apx1.");
    expect(await axeViolations(page)).toEqual([]);
    await capture(page, "ficha-historial-socio-stack", "light", 1440);
    await page.emulateMedia({ colorScheme: "dark" });
    expect(await axeViolations(page)).toEqual([]);
    await capture(page, "ficha-historial-socio-stack", "dark", 1440);
    await page.emulateMedia({ colorScheme: "light" });
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(frases.first()).toBeVisible();
    await capture(page, "ficha-historial-socio-stack-movil", "light", 390);
  });
});
