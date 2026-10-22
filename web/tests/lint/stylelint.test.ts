// @vitest-environment node
// US-068 T2 (criterio 1): Stylelint, con la configuración del repo, no encuentra ningún error
// en los CSS reales de src/ (colores y fuentes literales incluidos), así que `npm test` falla
// igual que `npm run lint` si un literal se cuela en shared/ui, layouts u otra carpeta. Los
// controles que deben fallar están en lint-controls.test.ts.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import stylelint from "stylelint";

const WEB_ROOT = fileURLToPath(new URL("../../", import.meta.url));
const SRC = join(WEB_ROOT, "src");

function cssFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return cssFiles(path);
    return name.endsWith(".css") ? [path] : [];
  });
}

const TOKEN_FILES = new Set(["tokens.css", "fonts.css"]);

describe("Stylelint sobre src/", () => {
  it("revisa los CSS Modules de shared/ui, layouts, core y features", () => {
    const files = cssFiles(SRC).map((f) => f.slice(SRC.length + 1).replace(/\\/g, "/"));
    for (const prefix of ["shared/ui/", "layouts/", "core/theme/", "features/"]) {
      expect(files.some((f) => f.startsWith(prefix)), prefix).toBe(true);
    }
  });

  it("no hay errores con la configuración del repo", async () => {
    const result = await stylelint.lint({ files: ["src/**/*.css"], cwd: WEB_ROOT });
    const errors = result.results.flatMap((r) =>
      r.warnings.filter((w) => w.severity === "error").map((w) => `${r.source ?? ""}:${String(w.line)} ${w.rule}`),
    );

    expect(errors).toEqual([]);
  }, 60_000);

  it("fuera de tokens.css y fonts.css ningún CSS declara colores ni familias literales", () => {
    for (const file of cssFiles(SRC).filter((f) => !TOKEN_FILES.has(f.split(/[\\/]/).pop() ?? ""))) {
      const css = readFileSync(file, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
      expect(css, file).not.toMatch(/#[0-9a-f]{3,8}\b/i);
      expect(css, file).not.toMatch(/\b(rgba?|hsla?|hwb|lab|lch|oklch|oklab)\(/i);
      expect(css, file).not.toMatch(/font-family\s*:(?!\s*(var\(|inherit))/);
    }
  });
});
