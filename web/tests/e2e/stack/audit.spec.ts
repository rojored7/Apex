// S4A-F1 (US-102 a US-104; S4A-D59, L-8) contra el stack de Compose (proyecto `stack`): el admin del
// seed (E2E_ADMIN_*) filtra la auditoría por la entidad Membresía, abre el detalle de una entrada que
// la propia spec genera (el alta de un coach desechable), pulsa "Verificar ahora" y ve la cadena
// íntegra; el coach ve "Sin permiso" en /sistema/auditoria. Sin aserciones sobre la primera página
// ni el número de filas: el worker y otras specs escriben en la auditoría a la vez. El coach se borra
// al terminar. axe en la lista y en el detalle. La variante simulada es ../audit.spec.ts.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { borrarUsuario, crearCoach, datosDeBase, esperarTransiciones, exigirStackLocal, loginComo, type CoachCreado } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
/** La verificación en segundo plano puede tardar; el tope del api es 900 s, la spec espera 120 s. */
const VERIFY_TIMEOUT_MS = 120_000;

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

test.describe("auditoría contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con B3 y B4; en preview corre audit.spec.ts");

  test("el admin filtra, abre un detalle y verifica la cadena; el coach no entra", async ({ page, browser }) => {
    test.setTimeout(VERIFY_TIMEOUT_MS + 60_000);
    exigirStackLocal(process.env.E2E_BASE_URL);
    const admin = datosDeBase();
    await page.setViewportSize({ width: 1440, height: 900 });
    let coach: CoachCreado | null = null;
    // Revisión de seguridad de F1 (LOW 4): el contexto del coach se cierra también si la spec falla.
    let coachContext: BrowserContext | null = null;
    try {
      coach = await crearCoach(page, admin);
      await loginComo(page, admin);

      // 1. Lista filtrada por entidad (los nombres del api en la URL).
      await page.goto("/sistema/auditoria");
      await expect(page.getByRole("heading", { level: 1, name: /Auditoría/ })).toBeVisible();
      await page.getByRole("combobox", { name: "Entidad" }).selectOption("memberships.memberships");
      await expect.poll(() => new URL(page.url()).searchParams.get("table")).toBe("memberships.memberships");
      await expect(page.getByRole("table", { name: "Auditoría" }).or(page.getByText("No hay entradas de auditoría con estos filtros"))).toBeVisible();
      expect(await axeViolations(page)).toEqual([]);

      // 2. Detalle de una entrada que existe seguro: el alta del coach (auth.users, su id).
      await page.goto(`/sistema/auditoria?table=auth.users&record_id=${coach.id}`);
      const table = page.getByRole("table", { name: "Auditoría" });
      await expect(table).toBeVisible();
      await table.getByRole("link").first().click();
      const panel = page.getByRole("dialog", { name: /^Entrada #\d+$/ });
      await expect(panel).toBeVisible();
      await expect.poll(() => new URL(page.url()).searchParams.get("seq")).toMatch(/^\d+$/);
      await expect(panel.getByText("Hash", { exact: true })).toBeVisible();
      await expect(panel.getByRole("button", { name: /mostrar|descifrar/i })).toHaveCount(0);
      expect(await axeViolations(page)).toEqual([]);
      await panel.getByRole("button", { name: "Cerrar", exact: true }).click();
      await expect(page.getByRole("dialog")).toHaveCount(0);

      // 3. Verificar ahora: 200 o 202 con sondeo; al final, cadena íntegra.
      await page.getByRole("button", { name: "Verificar ahora" }).click();
      await expect(page.getByText(/^Cadena íntegra: [\d.]+ filas verificadas/)).toBeVisible({ timeout: VERIFY_TIMEOUT_MS });

      // 4. El coach ve Sin permiso.
      coachContext = await browser.newContext({ viewport: { width: 1440, height: 900 } });
      const coachPage = await coachContext.newPage();
      await loginComo(coachPage, coach);
      await coachPage.goto("/sistema/auditoria");
      await expect(coachPage.getByRole("heading", { level: 1, name: "Sin permiso" })).toBeVisible();
      await expect(coachPage.getByRole("navigation", { name: "Menú principal" }).getByRole("link", { name: "Auditoría" })).toHaveCount(0);
    } finally {
      await coachContext?.close();
      if (coach) await borrarUsuario(page, coach.id, admin);
    }
  });
});
