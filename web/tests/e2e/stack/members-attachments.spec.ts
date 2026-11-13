// S6-F3 (US-148, US-150) contra el stack de Compose: la pestaña Adjuntos de la ficha. El admin crea por
// el api un socio, sube la autorización de datos (cuerpo crudo, ?kind=consent) y la descarga desde la
// pestaña con "Descargar" (a[download], sin abrir una pestaña); el archivo baja descifrado con el
// nombre adjunto-<8 hex>.pdf y la tabla marca "Cifrado". axe en claro y oscuro. Escrito para V7 (el
// ensayo de producción): no se corre en F3. Credenciales: E2E_ADMIN_EMAIL y E2E_ADMIN_PASSWORD.
// Sin E2E_BASE_URL se omite.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { capture, datosDeBase, documentoAleatorio, esperarTransiciones, loginComo, sameOriginHeaders } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const API = "/api/v1";
const PDF = Buffer.from("%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n");

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

test.describe("pestaña Adjuntos de la ficha contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con S6-C2, S6-C4 y S6-F3");

  let socioId: string | null = null;
  let token = "";

  test.afterEach(async ({ page }) => {
    if (socioId) await page.request.delete(`${API}/members/${socioId}`, { headers: { ...sameOriginHeaders(), Authorization: `Bearer ${token}` } });
    socioId = null;
  });

  test("subir la autorización por el api y descargarla desde la pestaña", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    token = await loginComo(page, datosDeBase());
    const headers = { ...sameOriginHeaders(), Authorization: `Bearer ${token}` };
    const creado = await page.request.post(`${API}/members`, {
      headers,
      data: { first_name: "Tomás", last_name: `Adjuntos${Date.now().toString(36)}`, document_type: "CC", document: documentoAleatorio(), data_consent: true },
    });
    expect(creado.ok()).toBe(true);
    socioId = ((await creado.json()) as { id: string }).id;
    const subida = await page.request.post(`${API}/members/${socioId}/attachments?kind=consent`, { headers: { ...headers, "Content-Type": "application/pdf" }, data: PDF });
    expect(subida.status()).toBe(201);

    await page.goto(`/socios/${socioId}`);
    await page.getByRole("tab", { name: "Adjuntos" }).click();
    await expect(page).toHaveURL(new RegExp(`/socios/${socioId}/adjuntos$`));
    const tabla = page.getByRole("table", { name: "Adjuntos del socio" });
    await expect(tabla.getByText("Autorización de datos")).toBeVisible();
    await expect(tabla.getByText("Cifrado")).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);
    await capture(page, "ficha-adjuntos-stack", "light", 1440);
    await capture(page, "ficha-adjuntos-stack", "dark", 1440);
    await page.emulateMedia({ colorScheme: "light" });

    const popup = page.waitForEvent("popup", { timeout: 1500 }).then(
      () => true,
      () => false,
    );
    const descarga = page.waitForEvent("download");
    await tabla.getByRole("button", { name: /^Descargar Autorización de datos/ }).click();
    const archivo = await descarga;
    expect(archivo.suggestedFilename()).toMatch(/^adjunto-[0-9a-f]{8}\.pdf$/);
    expect(await popup).toBe(false);
  });
});
