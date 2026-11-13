// S6-F4 (US-148, US-149) contra el stack de Compose, por Nginx: el alta con foto sube la imagen como cuerpo
// crudo (?kind=photo) y la ficha la muestra en memoria (blob:). El tope es exacto: 5.242.880 bytes pasa y
// 5.242.881 muestra «La foto supera 5 MB» sin perder el formulario. axe en claro y oscuro. Escrito para V7
// (el ensayo de producción): NO se corre en F4. Credenciales: E2E_ADMIN_EMAIL y E2E_ADMIN_PASSWORD.
// Sin E2E_BASE_URL se omite.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { capture, datosDeBase, documentoAleatorio, esperarTransiciones, loginComo, sameOriginHeaders } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const API = "/api/v1";
const MAX_BYTES = 5 * 1024 * 1024;

// PNG válido de 1x1 píxel completado con ceros tras IEND hasta `size` bytes: los lectores de imagen
// ignoran lo que sigue a IEND y el api valida por bytes mágicos y tamaño.
function pngDeTamano(size: number): Buffer {
  const base = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", "base64");
  return Buffer.concat([base, Buffer.alloc(size - base.length)]);
}

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

test.describe("alta con foto contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con S6-C2 y S6-F4");

  let token = "";
  let socioId: string | null = null;

  test.afterEach(async ({ page }) => {
    if (socioId) await page.request.delete(`${API}/members/${socioId}`, { headers: { ...sameOriginHeaders(), Authorization: `Bearer ${token}` } });
    socioId = null;
  });

  test("5.242.880 bytes pasa por Nginx y se ve en la ficha; 5.242.881 muestra el mensaje y no pierde el formulario", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    token = await loginComo(page, datosDeBase());
    await page.goto("/socios/nuevo");

    const apellido = `Foto${Date.now().toString(36)}`;
    await page.getByRole("textbox", { name: /^Nombres/ }).fill("Tomás");
    await page.getByRole("textbox", { name: /^Apellidos/ }).fill(apellido);
    await page.getByRole("textbox", { name: /^Número de documento/ }).fill(documentoAleatorio());

    await page.getByLabel(/^Foto del socio/).setInputFiles({ name: "grande.png", mimeType: "image/png", buffer: pngDeTamano(MAX_BYTES + 1) });
    await expect(page.getByText(/^La foto supera 5 MB/)).toBeVisible();
    await expect(page.getByRole("textbox", { name: /^Apellidos/ })).toHaveValue(apellido);
    expect(await axeViolations(page)).toEqual([]);
    await capture(page, "socio-nuevo-foto-excede-stack", "light", 1440);
    await capture(page, "socio-nuevo-foto-excede-stack", "dark", 1440);
    await page.emulateMedia({ colorScheme: "light" });

    await page.getByLabel(/^Foto del socio/).setInputFiles({ name: "justa.png", mimeType: "image/png", buffer: pngDeTamano(MAX_BYTES) });
    await expect(page.getByRole("img", { name: "Vista previa de la foto" })).toBeVisible();
    const subida = page.waitForResponse((r) => /\/members\/[^/]+\/attachments\?kind=photo$/.test(r.url()) && r.request().method() === "POST");
    await page.getByRole("button", { name: "Guardar" }).click();
    const respuesta = await subida;
    expect(respuesta.status()).toBe(201);
    socioId = /\/members\/([^/]+)\/attachments/.exec(respuesta.url())?.[1] ?? null;
    await expect(page).toHaveURL(/\/socios$/);

    await page.goto(`/socios/${socioId ?? ""}`);
    await expect(page.getByRole("img", { name: "Foto del socio" })).toBeVisible();
  });
});
