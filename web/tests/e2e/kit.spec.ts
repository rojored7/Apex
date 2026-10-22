// US-068 T6 (criterios 4 y 5): catálogo del kit y los cuatro layouts en claro y oscuro, a 320,
// 768, 1024 y 1440 px, con axe-core (wcag2a, wcag2aa y wcag21aa: contraste, nombre accesible,
// rol y foco), sin desplazamiento horizontal y con captura en
// test-results/captures/<tema>-<ancho>.png.
// axe-core se inyecta desde node_modules (ya es dependencia de vitest-axe): no hace falta
// @axe-core/playwright (MPL-2.0) para correr las mismas reglas.
import { expect, test, type Page } from "@playwright/test";
import { createRequire } from "node:module";

const AXE_PATH = createRequire(import.meta.url).resolve("axe-core/axe.min.js");
const WIDTHS = [320, 768, 1024, 1440] as const;
const THEMES = ["light", "dark"] as const;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];

interface AxeViolation {
  id: string;
  impact: string | null;
  help: string;
  nodes: { target: string[] }[];
}

async function axeViolations(page: Page): Promise<string[]> {
  await page.addScriptTag({ path: AXE_PATH });
  const violations = await page.evaluate(async (tags) => {
    const axe = (window as unknown as { axe: { run: (ctx: Document, opts: object) => Promise<{ violations: AxeViolation[] }> } }).axe;
    const result = await axe.run(document, { runOnly: { type: "tag", values: tags } });
    return result.violations;
  }, TAGS);
  return violations.map((v) => `${v.id} (${v.impact ?? "?"}): ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

async function noHorizontalOverflow(page: Page): Promise<void> {
  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
}

for (const theme of THEMES) {
  for (const width of WIDTHS) {
    test(`catálogo en ${theme} a ${String(width)} px: axe sin violaciones y sin desborde`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: theme });
      await page.setViewportSize({ width, height: 900 });
      await page.goto(`/catalog.html?tema=${theme}`);

      await expect(page.getByRole("heading", { level: 1, name: "Kit de componentes" })).toBeVisible();
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      expect(await axeViolations(page)).toEqual([]);
      await noHorizontalOverflow(page);
      await page.screenshot({ path: `test-results/captures/${theme}-${String(width)}.png`, fullPage: true });
    });
  }
}

const LAYOUTS = [
  { view: "panel&rol=admin", width: 1440, height: 900 },
  { view: "panel&rol=coach", width: 390, height: 844 },
  { view: "portal", width: 390, height: 844 },
  { view: "gym", width: 1024, height: 768 },
  { view: "tv", width: 1920, height: 1080 },
] as const;

for (const theme of THEMES) {
  for (const { view, width, height } of LAYOUTS) {
    test(`layout ${view} en ${theme}: axe sin violaciones`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: theme });
      await page.setViewportSize({ width, height });
      await page.goto(`/catalog.html?vista=${view}&tema=${theme}`);
      await page.waitForLoadState("networkidle");

      expect(await axeViolations(page)).toEqual([]);
      await noHorizontalOverflow(page);
    });
  }
}

test("el conmutador de tema del catálogo cambia el tema y el texto del botón", async ({ page }) => {
  await page.goto("/catalog.html");
  const toggle = page.getByRole("button", { name: "Cambiar a tema oscuro" }).first();

  await toggle.click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.getByRole("button", { name: "Cambiar a tema claro" }).first()).toBeFocused();
});

test("con localStorage bloqueado el conmutador sigue funcionando", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get() {
        throw new DOMException("bloqueado", "SecurityError");
      },
    });
  });
  await page.goto("/catalog.html");

  await page.getByRole("button", { name: "Cambiar a tema oscuro" }).first().click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});
