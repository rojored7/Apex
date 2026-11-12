// S6-F1 (US-142; S6-D62, D81) contra el ensayo de Compose (proyecto `stack`, en V7): la firma está
// presente tras `docker compose run --rm worker python -m app.worker.main --run-once sign_audit`
// (lo corre quien opera el ensayo, antes de esta spec) y «Verificar ahora» cuenta las firmas válidas.
// Solo lectura y verificación; no crea datos. axe en claro y oscuro. La variante simulada es ../audit.spec.ts.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { datosDeBase, esperarTransiciones, exigirStackLocal, loginComo } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const VERIFY_TIMEOUT_MS = 120_000;

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

test.describe("firma de la auditoría contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) tras --run-once sign_audit; en preview corre audit.spec.ts");

  test("hay una firma Ed25519 y Verificar ahora cuenta las firmas válidas", async ({ page }) => {
    test.setTimeout(VERIFY_TIMEOUT_MS + 60_000);
    exigirStackLocal(process.env.E2E_BASE_URL);
    await page.setViewportSize({ width: 1440, height: 900 });
    await loginComo(page, datosDeBase());

    await page.goto("/sistema/auditoria");
    const block = page.getByRole("region", { name: "Firma de la cadena" });
    await expect(block).toBeVisible();
    await expect(block.getByText("Sin firmas")).toHaveCount(0);
    await expect(block.getByText(/Última firma (válida|registrada): seq \d+ · .* · Ed25519/)).toBeVisible();

    await page.getByRole("button", { name: "Verificar ahora" }).click();
    const counted = page.getByText(/^Firmas verificadas: (\d+) de \1 válidas$/);
    await expect(counted).toBeVisible({ timeout: VERIFY_TIMEOUT_MS });
    await expect(page.getByText(/Firma alterada/)).toHaveCount(0);
    await expect(block.getByText("Íntegra").or(block.getByText("Firma atrasada"))).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);

    await page.emulateMedia({ colorScheme: "dark" });
    expect(await axeViolations(page)).toEqual([]);
  });
});
