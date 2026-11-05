// S5-F1 (US-127, US-128, US-129) y S5-F2 contra el stack de Compose (ensayo, V5 del Sprint 5): el admin abre
// /avisos/hoy, "Abrir WhatsApp" hace el POST real (200, aviso `sent`, wa.me con noopener,noreferrer) y
// "Omitir" guarda el motivo. Necesita B7 y avisos generados (`tools notify --generate-only`); sin
// avisos de WhatsApp pendientes la prueba se omite con una anotación. Sin E2E_BASE_URL se omite: la
// variante contra `vite preview` es ../avisos.spec.ts. window.open se observa: no sale nada del navegador.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { esperarTransiciones, exigirStackLocal, habilitarWhatsapp, loginComo } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

async function observarWindowOpen(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const opened: unknown[][] = [];
    (window as unknown as { __opened: unknown[][] }).__opened = opened;
    window.open = (...args: unknown[]) => {
      opened.push(args);
      return null;
    };
  });
}

test.describe("por avisar hoy contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con B7; en preview corre avisos.spec.ts");

  test("abrir WhatsApp marca el aviso como enviado y omitir guarda el motivo", async ({ page }) => {
    exigirStackLocal(process.env.E2E_BASE_URL);
    await page.setViewportSize({ width: 1440, height: 900 });
    await observarWindowOpen(page);
    await loginComo(page);
    await habilitarWhatsapp(page); // S5-D265: sin el canal encendido no hay avisos ni enlace de WhatsApp
    await page.goto("/avisos/hoy");
    await expect(page.getByRole("heading", { level: 1, name: /^Por avisar hoy · / })).toBeVisible();

    const botones = page.getByRole("button", { name: /^Abrir WhatsApp de / });
    await expect(botones.first().or(page.getByText("Nadie por avisar hoy"))).toBeVisible();
    if ((await botones.count()) < 2) {
      test.info().annotations.push({ type: "sin-avisos", description: "Hacen falta 2 avisos de WhatsApp pendientes: corre `tools notify --generate-only` en el ensayo." });
      test.skip(true, "sin avisos de WhatsApp pendientes en el ensayo");
    }
    expect(await axeViolations(page)).toEqual([]);

    const primero = await botones.first().getAttribute("aria-label");
    const nombre = (primero ?? "").replace("Abrir WhatsApp de ", "");
    const respuesta = page.waitForResponse((r) => r.url().includes("/wa-link") && r.request().method() === "POST");
    await botones.first().click();
    expect((await respuesta).status()).toBe(200);
    await expect(page.getByText(`WhatsApp abierto para ${nombre}. El aviso quedó marcado como enviado.`)).toBeVisible();
    const opened = (await page.evaluate(() => (window as unknown as { __opened: unknown[][] }).__opened)) as [string, string, string][];
    expect(opened).toHaveLength(1);
    expect(opened[0]?.[0]).toMatch(/^https:\/\/wa\.me\/57\d+/);
    expect(opened[0]?.slice(1)).toEqual(["_blank", "noopener,noreferrer"]);

    // V5: la fila enviada sale de la lista al refrescar; sin esta espera `first()` podía tomar su botón y el diálogo abría otro aviso.
    await expect(page.getByRole("button", { name: `Omitir aviso de ${nombre}` })).toHaveCount(0);
    const omitir = page.getByRole("button", { name: /^Omitir aviso de / }).first();
    const otro = ((await omitir.getAttribute("aria-label")) ?? "").replace("Omitir aviso de ", "");
    await omitir.click();
    const dialog = page.getByRole("dialog", { name: `¿Omitir el aviso de ${otro}?` });
    await dialog.getByRole("textbox", { name: /^Motivo/ }).fill("Prueba E2E del ensayo");
    const skip = page.waitForResponse((r) => r.url().includes("/skip") && r.request().method() === "POST");
    await dialog.getByRole("button", { name: "Omitir aviso" }).click();
    expect((await skip).status()).toBe(200);
    await expect(page.getByText(`Aviso de ${otro} omitido. Quedó en el historial con tu motivo.`)).toBeVisible();
  });
});

// S5-F2 (US-120, US-121, US-122, US-130): las pantallas de solo lectura contra el ensayo, sin dejar datos:
// reglas y plantillas sembradas (S5-B6), vista previa real, historial y la pestaña Canales de Configuración
// (credentials_present real). Se corre en V5.
test.describe("reglas, plantillas, historial y canales contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con B6 y B7; en preview corre avisos.spec.ts");

  test("el admin ve las reglas sembradas, la vista previa de una plantilla, el historial y los canales", async ({ page }) => {
    exigirStackLocal(process.env.E2E_BASE_URL);
    await page.setViewportSize({ width: 1440, height: 900 });
    await loginComo(page);

    await page.goto("/avisos/reglas");
    await expect(page.getByRole("heading", { level: 1, name: "Avisos" })).toBeVisible();
    await expect(page.getByRole("table", { name: "Reglas" }).getByRole("row").nth(1)).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);

    await page.getByRole("tab", { name: "Plantillas" }).click();
    await page.getByRole("button", { name: /^Editar plantilla / }).first().click();
    const preview = page.waitForResponse((r) => r.url().includes("/notification-templates/preview") && r.request().method() === "POST");
    await page.getByRole("button", { name: "Ver vista previa" }).click();
    expect((await preview).status()).toBe(200);
    await expect(page.getByRole("region", { name: "Vista previa" })).toBeVisible();
    await page.getByRole("button", { name: "Cerrar" }).click();

    await page.goto("/avisos/historial");
    await expect(page.getByRole("heading", { level: 1, name: "Historial de envíos" })).toBeVisible();
    await expect(page.getByRole("table", { name: "Historial de envíos" }).or(page.getByText("Todavía no hay envíos."))).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);

    await page.goto("/sistema/configuracion?tab=canales");
    await expect(page.getByRole("group", { name: "Correo" }).getByText(/Credenciales listas|Faltan credenciales en \.env/)).toBeVisible();
    await expect(page.locator("input[type=password]")).toHaveCount(0);
    expect(await axeViolations(page)).toEqual([]);
  });
});
