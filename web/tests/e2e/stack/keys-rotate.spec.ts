// S6-F2 (US-143 a US-146; V4 del Sprint 6) contra el ensayo de Compose (proyecto `stack`, en V7): rotar
// `member.phone` desde la pantalla. ESCRITO, NO CORRIDO en F2: lo corre quien opera el ensayo con el worker
// encendido y OpenBao desellado.
// - Inventario sin material (ningún `vault:` en la página), «Rotar» con motivo y ROTAR exacto, salto a Trabajos.
// - Durante la rotación un admin lee el teléfono de un socio (POST /members/{id}/reveal) y sigue siendo el
//   correcto; al terminar, la versión 2 queda activa y la 1 en «solo descifrar».
// - «Exportar CBOM» baja apex-cbom-AAAA-MM-DD.json sin material de llave.
// - axe en claro y oscuro. Credenciales: E2E_ADMIN_EMAIL y E2E_ADMIN_PASSWORD. Sin E2E_BASE_URL se omite.
// Deja un socio creado por la spec, que borra al terminar; la rotación en sí es un efecto del ensayo (la
// llave nueva queda), por eso solo se corre contra el ensayo desechable.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { capture, datosDeBase, documentoAleatorio, esperarTransiciones, exigirStackLocal, loginComo, sameOriginHeaders } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const API = "/api/v1";
const PHONE = "3001234567";
const ROTATION_TIMEOUT_MS = 180_000;

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

test.describe("rotación de member.phone desde la pantalla de llaves contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con S6-R1 y S6-F2; en preview corre keys.spec.ts");

  let socioId: string | null = null;
  let token = "";

  test.afterEach(async ({ page }) => {
    if (socioId) await page.request.delete(`${API}/members/${socioId}`, { headers: { ...sameOriginHeaders(), Authorization: `Bearer ${token}` } });
    socioId = null;
  });

  test("rota, el socio se sigue leyendo durante el proceso y el CBOM se descarga", async ({ page }) => {
    test.setTimeout(ROTATION_TIMEOUT_MS + 120_000);
    exigirStackLocal(process.env.E2E_BASE_URL);
    await page.setViewportSize({ width: 1440, height: 900 });
    token = await loginComo(page, datosDeBase());
    const headers = { ...sameOriginHeaders(), Authorization: `Bearer ${token}` };
    const creado = await page.request.post(`${API}/members`, {
      headers,
      data: { first_name: "Tomás", last_name: `Rotar${Date.now().toString(36)}`, document_type: "CC", document: documentoAleatorio(), phone: PHONE, data_consent: true },
    });
    expect(creado.ok()).toBe(true);
    socioId = ((await creado.json()) as { id: string }).id;

    await page.goto("/sistema/llaves");
    const inventario = page.getByRole("table", { name: "Inventario de llaves" });
    await expect(inventario.getByText("member.phone").first()).toBeVisible();
    expect(await page.content()).not.toContain("vault:");
    expect(await axeViolations(page)).toEqual([]);
    await capture(page, "llaves-stack", "light", 1440);
    await capture(page, "llaves-stack", "dark", 1440);
    await page.emulateMedia({ colorScheme: "light" });

    // V7: la versión activa de cifrado de member.phone depende de las rotaciones previas del ensayo; se lee antes de rotar.
    const activa = (await inventario.getByRole("row", { name: /member\.phone Cifrado.*Activa/ }).first().innerText()).replace(/\s+/g, " ");
    const previa = Number(/ v(\d+) /.exec(activa)?.[1] ?? Number.NaN);
    expect(Number.isInteger(previa)).toBe(true);

    await page.getByRole("button", { name: "Rotar member.phone" }).click();
    const dialog = page.getByRole("dialog", { name: "¿Rotar la llave de member.phone?" });
    await dialog.getByLabel(/^Motivo/).fill("Rotación de ensayo V4");
    await dialog.getByRole("textbox", { name: "Escribe ROTAR para confirmar" }).fill("ROTAR");
    await dialog.getByRole("button", { name: "Rotar llave" }).click();
    await expect(page.getByRole("tab", { name: "Trabajos" })).toHaveAttribute("aria-selected", "true");

    // Durante la rotación (mientras el trabajo no esté terminado) el teléfono se sigue revelando bien.
    const revelar = async (): Promise<string | null> => {
      const response = await page.request.post(`${API}/members/${socioId ?? ""}/reveal`, { headers, data: { field: "phone" } });
      expect(response.ok()).toBe(true);
      return ((await response.json()) as { value: string | null }).value;
    };
    expect(await revelar()).toBe(PHONE);
    const jobs = page.getByRole("table", { name: "Trabajos de rotación y recifrado" });
    await expect(jobs.getByText("Rotación").first()).toBeVisible();
    await expect(jobs.getByText("Terminado").first()).toBeVisible({ timeout: ROTATION_TIMEOUT_MS });
    expect(await revelar()).toBe(PHONE);
    expect(await axeViolations(page)).toEqual([]);

    await page.getByRole("tab", { name: "Inventario" }).click();
    const fila = (version: number, estado: string) => inventario.getByRole("row", { name: new RegExp(`member\\.phone Cifrado.* v${String(version)} .*${estado}`) });
    await expect(fila(previa + 1, "Activa")).toBeVisible();
    await expect(fila(previa, "Solo descifrar")).toBeVisible();

    const descarga = page.waitForEvent("download");
    await page.getByRole("button", { name: "Exportar CBOM" }).click();
    const archivo = await descarga;
    expect(archivo.suggestedFilename()).toMatch(/^apex-cbom-\d{4}-\d{2}-\d{2}\.json$/);
    const ruta = await archivo.path();
    const cbom = await readFile(ruta, "utf8");
    expect(cbom).not.toMatch(/vault:|wrapped|BEGIN /);
    expect(() => {
      JSON.parse(cbom);
    }).not.toThrow();
  });
});
