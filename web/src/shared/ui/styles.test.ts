// @vitest-environment node
// Verificación estática de los CSS Modules: jsdom no calcula alturas ni estilos de foco.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

type ModuleName = "Button" | "Field" | "StatusTag";

function readModule(name: ModuleName): string {
  return readFileSync(fileURLToPath(new URL(`./${name}.module.css`, import.meta.url)), "utf8");
}

/** Cuerpos de las reglas cuyo selector contiene `selector` (sin anidamiento). */
function ruleBodies(css: string, selector: RegExp): string[] {
  const withoutComments = css.replace(/\/\*[\s\S]*?\*\//g, "");
  const rules = [...withoutComments.matchAll(/([^{}]+)\{([^{}]*)\}/g)];
  return rules.filter((rule) => selector.test(rule[1] ?? "")).map((rule) => rule[2] ?? "");
}

const FOCUS_RING = /(outline|box-shadow)\s*:[^;]*var\(--(blue-deep|apex-blue)\)/;

describe("estilos de los componentes base", () => {
  it("Button usa 44 px en md y 56 px en lg", () => {
    const css = readModule("Button");

    expect(ruleBodies(css, /\.md\b/).join(";")).toMatch(/min-height\s*:\s*var\(--control\)/);
    expect(ruleBodies(css, /\.lg\b/).join(";")).toMatch(/min-height\s*:\s*var\(--control-gym\)/);
  });

  it("el control de Field usa 44 px en md y 56 px en lg", () => {
    const css = readModule("Field");

    expect(ruleBodies(css, /\.control\b/).join(";")).toMatch(/min-height\s*:\s*var\(--control\)/);
    expect(ruleBodies(css, /\.lg\b/).join(";")).toMatch(/min-height\s*:\s*var\(--control-gym\)/);
  });

  it.each<ModuleName>(["Button", "Field", "StatusTag"])("%s tiene foco visible con borde azul de tokens", (name) => {
    const focus = ruleBodies(readModule(name), /:focus-visible/).join(";");

    expect(focus).toMatch(FOCUS_RING);
  });

  it.each<ModuleName>(["Button", "Field", "StatusTag"])("%s no tiene colores literales", (name) => {
    const css = readModule(name);

    expect(css).not.toMatch(/#[0-9a-f]{3,8}\b/i);
    expect(css).not.toMatch(/\b(rgba?|hsla?)\(/i);
    expect(css).toMatch(/var\(--/);
  });

  it("marca los dos huecos de diseño conocidos", () => {
    expect(readModule("Button")).toContain("/* DESIGN-GAP: variante ghost no definida en DESIGN.md */");
    expect(readModule("StatusTag")).toContain("/* DESIGN-GAP: estilo de Cancelado no definido; se usa el de Congelado */");
  });
});
