// S5-F1 (US-127, US-128, US-129) contra el stack de Compose (ensayo, V5 del Sprint 5): el admin abre
// /avisos/hoy, "Abrir WhatsApp" hace el POST real (200, aviso `sent`, wa.me con noopener,noreferrer) y
// "Omitir" guarda el motivo. Necesita B7 y avisos generados (`tools notify --generate-only`); sin
// avisos de WhatsApp pendientes la prueba se omite con una anotación. Sin E2E_BASE_URL se omite: la
// variante contra `vite preview` es ../avisos.spec.ts. window.open se observa: no sale nada del navegador.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { esperarTransiciones, exigirStackLocal, loginComo } from "../helpers/stack";

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
