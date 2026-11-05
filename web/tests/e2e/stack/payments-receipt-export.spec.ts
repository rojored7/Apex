// S5-F4 (US-137, US-139; S5-D40, S5-D41, L-8) contra el stack de Compose (proyecto `stack`). El admin
// crea por el api un socio y un plan, le vende la membresía con el pago completo por Nequi y, en
// /pagos: descarga el recibo PDF desde la fila ("recibo-<8 hex>.pdf", empieza por %PDF) y desde el
// detalle; exporta los pagos de hoy (rango obligatorio) y comprueba el CSV (BOM, separador `;`,
// cabecera de N-29 y la fila del pago); sin rango, el modal lo explica y no hay descarga. El coach ve
// "Recibo" pero no "Exportar". axe en la lista y en el modal. Se corre contra el ensayo en V5 (sin
// Docker desde el worktree); sin E2E_BASE_URL se omite.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type BrowserContext, type Download, type Page } from "@playwright/test";
import { borrarUsuario, crearCoach, crearPlan, crearSocio, darDeBajaPlan, darDeBajaSocio, datosDeBase, esperarTransiciones, exigirStackLocal, fechaBogota, loginComo, venderMembresia, type CoachCreado, type PlanCreado, type SocioCreado } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const EXPORT_NOTE = "La descarga contiene datos personales y queda registrada en la auditoría";

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

async function contenido(download: Download): Promise<Buffer> {
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream) chunks.push(chunk as Buffer);
  return Buffer.concat(chunks);
}

test.describe("recibo y exportación de pagos contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con B11 y B12 y la pantalla de pagos; se corre en V5");

  test("recibo desde la fila y el detalle, exportación con rango y el coach sin Exportar", async ({ page, browser }) => {
    exigirStackLocal(process.env.E2E_BASE_URL);
    await page.setViewportSize({ width: 1440, height: 900 });
    const admin = datosDeBase();
    let socio: SocioCreado | null = null;
    let plan: PlanCreado | null = null;
    let coach: CoachCreado | null = null;
    let coachContext: BrowserContext | null = null;
    try {
      socio = await crearSocio(page);
      plan = await crearPlan(page);
      await venderMembresia(page, socio.id, plan.id, { amount_cop: 120_000, method: "nequi", reference: `E2E-${Date.now().toString(36)}` });
      await loginComo(page, admin);

      // 1. Recibo desde la fila.
      await page.goto("/pagos");
      await page.getByRole("searchbox", { name: "Buscar" }).fill(socio.documento);
      const row = page.getByRole("row", { name: new RegExp(socio.nombre) }).first();
      await expect(row).toBeVisible();
      expect(await axeViolations(page)).toEqual([]);
      const rowDownload = page.waitForEvent("download");
      await row.getByRole("button", { name: `Descargar el recibo del pago de ${socio.nombre}` }).click();
      const receipt = await rowDownload;
      expect(receipt.suggestedFilename()).toMatch(/^recibo-[0-9a-f]{8}\.pdf$/);
      expect((await contenido(receipt)).subarray(0, 4).toString("latin1")).toBe("%PDF");

      // 2. Recibo desde el detalle.
      await row.getByRole("button", { name: `Ver el pago de ${socio.nombre}` }).click();
      const detail = page.getByRole("dialog", { name: "Detalle del pago" });
      await expect(detail).toBeVisible();
      const detailDownload = page.waitForEvent("download");
      await detail.getByRole("button", { name: "Descargar el recibo del pago" }).click();
      expect((await detailDownload).suggestedFilename()).toMatch(/^recibo-[0-9a-f]{8}\.pdf$/);
      await detail.getByRole("button", { name: "Cerrar" }).click();

      // 3. Exportar sin rango: el modal lo explica y no hay descarga.
      await page.getByRole("button", { name: "Exportar" }).click();
      const modal = page.getByRole("dialog", { name: "¿Exportar los pagos?" });
      await expect(modal).toContainText(EXPORT_NOTE);
      await modal.getByRole("button", { name: "Descargar CSV" }).click();
      await expect(modal.getByRole("alert")).toContainText("Elige la fecha 'Desde'");
      expect(await axeViolations(page)).toEqual([]);
      await modal.getByRole("button", { name: "Volver" }).click();

      // 4. Exportar los pagos de hoy: BOM, `;`, cabecera de N-29 y la fila del pago.
      const hoy = fechaBogota();
      await page.goto(`/pagos?from=${hoy}&to=${hoy}`);
      await page.getByRole("searchbox", { name: "Buscar" }).fill(socio.documento);
      await expect(page.getByRole("row", { name: new RegExp(socio.nombre) }).first()).toBeVisible();
      await page.getByRole("button", { name: "Exportar" }).click();
      const csvDownload = page.waitForEvent("download");
      await page.getByRole("dialog", { name: "¿Exportar los pagos?" }).getByRole("button", { name: "Descargar CSV" }).click();
      const csv = await csvDownload;
      expect(csv.suggestedFilename()).toMatch(/^pagos-\d{8}\.csv$/);
      const bytes = await contenido(csv);
      expect([...bytes.subarray(0, 3)]).toEqual([0xef, 0xbb, 0xbf]);
      const text = bytes.subarray(3).toString("utf8");
      expect(text.split("\r\n")[0]).toBe("fecha;socio;plan;monto;medio;referencia;registrado_por;anulado;motivo_anulacion");
      expect(text).toContain(socio.nombre);
      await expect(page.getByRole("dialog")).toHaveCount(0);

      // 5. El coach ve "Recibo" pero no "Exportar".
      coach = await crearCoach(page);
      coachContext = await browser.newContext({ viewport: { width: 1440, height: 900 } });
      const coachPage = await coachContext.newPage();
      await loginComo(coachPage, coach);
      await coachPage.goto("/pagos");
      await coachPage.getByRole("searchbox", { name: "Buscar" }).fill(socio.documento);
      await expect(coachPage.getByRole("button", { name: `Descargar el recibo del pago de ${socio.nombre}` }).first()).toBeVisible();
      await expect(coachPage.getByRole("button", { name: "Exportar" })).toHaveCount(0);
    } finally {
      if (coach) await borrarUsuario(page, coach.id, admin);
      await coachContext?.close();
      if (socio) await darDeBajaSocio(page, socio.id, admin);
      if (plan) await darDeBajaPlan(page, plan.id, { admin, tolerante: () => undefined });
    }
  });
});
