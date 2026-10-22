// @vitest-environment node
// Todos los CSS Modules de src/shared/ui usan solo variables de tokens.css: sin colores ni
// fuentes literales, y con foco visible en azul cuando tienen controles. Complementa a
// Stylelint (que ya lo exige en `npm run lint`) para que `npm test` también lo vea.
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

const DIR = fileURLToPath(new URL("./", import.meta.url));
const MODULES = readdirSync(DIR).filter((f) => f.endsWith(".module.css"));
const NEW_IN_SPRINT_1 = [
  "PageHeader",
  "Tabs",
  "KpiCard",
  "SidePanel",
  "ConfirmModal",
  "DataTable",
  "Pagination",
  "FilterBar",
  "Chips",
  "MaskedValue",
  "HistoryAside",
];
// US-061: barra superior y menú lateral.
const NEW_IN_SPRINT_2 = ["TopBar", "SideNav"];
const WITH_FOCUS = [...NEW_IN_SPRINT_1, ...NEW_IN_SPRINT_2];

const read = (file: string): string => readFileSync(`${DIR}${file}`, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

describe("CSS Modules del kit compartido", () => {
  it("incluye los módulos del Sprint 1", () => {
    for (const name of WITH_FOCUS) expect(MODULES).toContain(`${name}.module.css`);
  });

  it.each(MODULES)("%s no tiene colores ni fuentes literales", (file) => {
    const css = read(file);

    expect(css).not.toMatch(/#[0-9a-f]{3,8}\b/i);
    expect(css).not.toMatch(/\b(rgba?|hsla?|hwb|lab|lch|oklch|oklab)\(/i);
    expect(css).not.toMatch(/font-family\s*:(?!\s*(var\(|inherit))/);
    expect(css).not.toMatch(/\bfont\s*:(?!\s*(var\(|inherit))/);
  });

  it.each(WITH_FOCUS.map((n) => `${n}.module.css`))("%s tiene foco visible con borde azul de tokens", (file) => {
    expect(read(file)).toMatch(/:focus-visible[^{]*\{[^}]*(outline|box-shadow)\s*:[^;]*var\(--(blue-deep|apex-blue)\)/);
  });
});
