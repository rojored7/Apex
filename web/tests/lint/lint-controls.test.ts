// @vitest-environment node
import { ESLint } from "eslint";
import { fileURLToPath } from "node:url";
import stylelint from "stylelint";

const WEB_ROOT = fileURLToPath(new URL("../../", import.meta.url));
const control = (name: string): string => fileURLToPath(new URL(`./${name}`, import.meta.url));

async function stylelintRules(file: string): Promise<string[]> {
  // Los controles están en ignoreFiles para que `npm run lint` los salte;
  // aquí se fuerza su revisión con la misma configuración.
  const result = await stylelint.lint({
    files: [control(file)],
    cwd: WEB_ROOT,
    disableDefaultIgnores: true,
    config: {
      extends: [fileURLToPath(new URL("../../.stylelintrc.json", import.meta.url))],
      ignoreFiles: [],
    },
  });
  return result.results.flatMap((r) => r.warnings.filter((w) => w.severity === "error").map((w) => w.rule));
}

async function eslintMessages(file: string): Promise<string[]> {
  const eslint = new ESLint({ cwd: WEB_ROOT, ignore: false });
  const [result] = await eslint.lintFiles([control(file)]);
  return (result?.messages ?? []).filter((m) => m.severity === 2).map((m) => m.ruleId ?? "fatal");
}

describe("lint de colores y fuentes literales", () => {
  it("Stylelint rechaza un color hex", async () => {
    expect(await stylelintRules("bad-hex.module.css")).toContain("color-no-hex");
  });

  it("Stylelint rechaza rgb()", async () => {
    expect(await stylelintRules("bad-rgb.module.css")).toContain("function-disallowed-list");
  });

  it("Stylelint rechaza font-family literal", async () => {
    expect(await stylelintRules("bad-font.module.css")).toContain("declaration-property-value-allowed-list");
  });

  it("Stylelint acepta colores y fuentes por variable", async () => {
    expect(await stylelintRules("good.module.css")).toEqual([]);
  });

  it("ESLint rechaza rgb() en un style en línea", async () => {
    expect(await eslintMessages("BadInline.tsx")).toContain("no-restricted-syntax");
  });

  it("ESLint rechaza hex y fontFamily en un style en línea", async () => {
    const messages = await eslintMessages("BadInlineHex.tsx");
    expect(messages.filter((m) => m === "no-restricted-syntax")).toHaveLength(2);
  });

  it("ESLint acepta un style en línea con variables", async () => {
    expect(await eslintMessages("GoodInline.tsx")).toEqual([]);
  });
}, 60_000);
