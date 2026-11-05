// S5-F4 (US-138; S5-D41, S5-D82, L-8) contra el stack de Compose (proyecto `stack`). El admin crea por
// el api un socio con documento aleatorio, en /socios lo busca (la búsqueda vive en memoria, nunca en
// la URL) y exporta: el modal confirma con el texto fijo de datos personales y auditoría, la descarga
// es "socios-AAAAMMDD.csv" con BOM y `;`, y trae al socio con su documento descifrado. El coach no
// ve "Exportar". Necesita el custodio de llaves desellado (si no, el modal muestra el 503 del api). axe en el modal. Se corre
// contra el ensayo en V5 (sin Docker desde el worktree); sin E2E_BASE_URL se omite.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { borrarUsuario, crearCoach, crearSocio, darDeBajaSocio, datosDeBase, esperarTransiciones, exigirStackLocal, loginComo, type CoachCreado, type SocioCreado } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const EXPORT_NOTE = "La descarga contiene datos personales y queda registrada en la auditoría";

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

test.describe("exportación de socios contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con B12 y la lista de socios; se corre en V5");

  test("el admin confirma y descarga el CSV con el socio; el coach no ve Exportar", async ({ page, browser }) => {
    exigirStackLocal(process.env.E2E_BASE_URL);
    await page.setViewportSize({ width: 1440, height: 900 });
    const admin = datosDeBase();
    let socio: SocioCreado | null = null;
    let coach: CoachCreado | null = null;
    let coachContext: BrowserContext | null = null;
    try {
      socio = await crearSocio(page);
      await loginComo(page, admin);

      await page.goto("/socios");
      await page.getByRole("searchbox", { name: "Buscar" }).fill(socio.documento);
      await expect(page.getByRole("link", { name: socio.nombre })).toBeVisible();
      expect(new URL(page.url()).search).not.toContain(socio.documento);

      await page.getByRole("button", { name: "Exportar" }).click();
      const modal = page.getByRole("dialog", { name: "¿Exportar la lista de socios?" });
      await expect(modal).toContainText(EXPORT_NOTE);
      expect(await axeViolations(page)).toEqual([]);

      const downloading = page.waitForEvent("download");
      await modal.getByRole("button", { name: "Descargar CSV" }).click();
      const download = await downloading;
      expect(download.suggestedFilename()).toMatch(/^socios-\d{8}\.csv$/);
      const stream = await download.createReadStream();
      const chunks: Buffer[] = [];
      for await (const chunk of stream) chunks.push(chunk as Buffer);
      const bytes = Buffer.concat(chunks);
      expect([...bytes.subarray(0, 3)]).toEqual([0xef, 0xbb, 0xbf]);
      const text = bytes.subarray(3).toString("utf8");
      expect(text.split("\r\n")[0]).toContain(";");
      expect(text).toContain(socio.nombre.split(" ")[1] ?? socio.nombre);
      expect(text).toContain(socio.documento);
      await expect(page.getByRole("dialog")).toHaveCount(0);

      coach = await crearCoach(page);
      coachContext = await browser.newContext({ viewport: { width: 1440, height: 900 } });
      const coachPage = await coachContext.newPage();
      await loginComo(coachPage, coach);
      await coachPage.goto("/socios");
      await expect(coachPage.getByRole("heading", { level: 1, name: "Socios" })).toBeVisible();
      await expect(coachPage.getByRole("button", { name: "Exportar" })).toHaveCount(0);
    } finally {
      if (coach) await borrarUsuario(page, coach.id, admin);
      await coachContext?.close();
      if (socio) await darDeBajaSocio(page, socio.id, admin);
    }
  });
});
