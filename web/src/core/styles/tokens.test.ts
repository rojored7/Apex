// @vitest-environment node
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const DESIGN_TOKENS = fileURLToPath(new URL("../../../../docs/design/tokens.css", import.meta.url));
const WEB_TOKENS = fileURLToPath(new URL("./tokens.css", import.meta.url));

function withoutImports(css: string): string {
  return css
    .split("\n")
    .filter((line) => !line.startsWith("@import"))
    .join("\n");
}

describe("tokens.css del front", () => {
  it("es la copia exacta de docs/design/tokens.css sin las líneas @import", () => {
    const original = readFileSync(DESIGN_TOKENS, "utf8");
    const copy = readFileSync(WEB_TOKENS, "utf8");

    expect(copy).toBe(withoutImports(original));
  });

  it("no pide nada a Google Fonts", () => {
    const copy = readFileSync(WEB_TOKENS, "utf8");

    expect(copy).not.toContain("fonts.googleapis.com");
    expect(copy).not.toContain("fonts.gstatic.com");
  });

  it("define las variables de marca", () => {
    const copy = readFileSync(WEB_TOKENS, "utf8");

    expect(copy).toContain("--apex-blue:");
    expect(copy).toContain("--text-screen-title:");
  });
});
